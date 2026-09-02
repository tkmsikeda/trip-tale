import json
import os
import re
import time
import logging
import boto3
from bs4 import BeautifulSoup
import requests
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")


def _make_filename(media_file: dict) -> str:
    """メディア情報からダウンロード先のファイル名を生成する

    Args:
        media_file (dict): メディアファイル情報
                          tookAt（ISO形式日時）と contentType を含む

    Returns:
        str: ファイル名（形式: YYYYMMDDHHMMss.{拡張子}）
    """
    captured_at = media_file["tookAt"]
    captured_at_datetime = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    timestamp_str = captured_at_datetime.strftime("%Y%m%d%H%M%S")
    extension = media_file["contentType"].split("/")[-1]
    return f"{timestamp_str}.{extension}"


def _make_download_url(media_file: dict, base_url: str) -> str:
    """メディア種別に応じて、ダウンロード先URLを返す

    Args:
        media_file (dict): メディアファイル情報（mediaType, uuid, expiringUrl を含む）
        base_url (str): アルバムのベースURL

    Returns:
        str: メディアダウンロード用のURL
    """
    if media_file.get("mediaType") == "movie":
        return f"{base_url}/media_files/{media_file['uuid']}/download"

    return media_file.get("expiringUrl") or (
        f"{base_url}/media_files/{media_file['uuid']}/download"
    )


def _find_gon_media_script_text(soup: BeautifulSoup) -> str | None:
    """JavaScript の gon.media オブジェクトを抽出

    Args:
        soup (BeautifulSoup): HTMLパース済みオブジェクト

    Returns:
        str | None: gon.media オブジェクトのJSON文字列、見つからない場合は None
    """
    for script in soup.find_all("script"):
        script_text = script.string
        if not script_text:
            continue
        if "gon.media" not in script_text:
            continue

        match = re.search(r"gon\.media\s*=\s*(\{)", script_text)
        if not match:
            continue

        start = match.start(1)
        depth = 0
        for i in range(start, len(script_text)):
            ch = script_text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return script_text[start : i + 1]

    return None


def _fetch_album_page(page_url: str, password: str | None = None) -> BeautifulSoup:
    """アルバムページのHTMLを取得して、BeautifulSoupオブジェクトを返す

    Args:
        page_url (str): アルバムページのURL
        password (str | None): みてねアルバムのパスワード（オプション）

    Returns:
        BeautifulSoup: パースされたHTMLオブジェクト

    Raises:
        requests.exceptions.HTTPError: HTTPリクエスト失敗時
    """
    params = {"password": password} if password else {}
    response = requests.get(page_url, params=params)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def _extract_album_data(soup: BeautifulSoup) -> dict:
    """アルバムページから、メディアダウンロードに必要なデータを抽出する

    Args:
        soup (BeautifulSoup): HTMLパース済みオブジェクト

    Returns:
        dict: gon.media オブジェクトのパース済み辞書
              mediaFiles, hasNext 等のキーを含む

    Raises:
        Exception: gon.media が見つからない場合
    """
    json_string = _find_gon_media_script_text(soup)
    if not json_string:
        raise Exception("Could not find JavaScript variable 'gon'")
    return json.loads(json_string)


def _download_media_files_to_s3(
    album_data: dict, base_url: str, s3_bucket: str, s3_prefix: str = "mitene-download"
) -> dict:
    """アルバムデータに基づいて、メディアをダウンロードしてS3に保存する

    Args:
        album_data (dict): アルバムデータ（mediaFiles キーを含む）
        base_url (str): アルバムのベースURL
        s3_bucket (str): S3バケット名
        s3_prefix (str): S3での保存パスプリフィックス（デフォルト: "mitene-download"）

    Returns:
        dict: 処理結果サマリー
              {
                  "total": 総メディア数,
                  "success": 成功数,
                  "failed": 失敗数,
                  "files": [{"filename": str, "s3_key": str}, ...]
              }
    """
    results = {
        "total": len(album_data["mediaFiles"]),
        "success": 0,
        "failed": 0,
        "files": [],
    }

    for media_file in album_data["mediaFiles"]:
        try:
            filename = _make_filename(media_file)
            s3_key = f"{s3_prefix}/{filename}"

            media_url = _make_download_url(media_file, base_url)

            logger.info(f"Downloading: {filename}")
            response = requests.get(media_url)
            response.raise_for_status()

            # S3にアップロード
            s3.put_object(
                Bucket=s3_bucket,
                Key=s3_key,
                Body=response.content,
                ContentType=media_file.get("contentType", "application/octet-stream"),
                Metadata={
                    "original-filename": filename,
                    "media-uuid": media_file.get("uuid", ""),
                    "media-type": media_file.get("mediaType", ""),
                },
            )

            logger.info(f"Uploaded to S3: s3://{s3_bucket}/{s3_key}")
            results["files"].append({"filename": filename, "s3_key": s3_key})
            results["success"] += 1

            # みてね負荷軽減のため1秒待機
            time.sleep(1)

        except Exception as e:
            logger.error(
                f"Failed to download/upload {media_file.get('uuid')}: {str(e)}"
            )
            results["failed"] += 1

    return results


def lambda_handler(event, context):
    """ワーカーLambda - SQS経由で呼ばれる（batch_size=1固定）

    1メッセージ = 1ページ = 1Lambda実行

    環境変数:
        S3_BUCKET_NAME (str): メディア保存先のS3バケット名（必須）
        MITENE_ALBUM_PASSWORD (str): アルバムパスワード（オプション）

    Returns:
        dict: Lambda実行結果
    """
    try:
        s3_bucket = os.getenv("S3_BUCKET_NAME")
        album_password = os.getenv("MITENE_ALBUM_PASSWORD")

        if not s3_bucket:
            raise ValueError("S3_BUCKET_NAME is not set")

        # SQSメッセージは batch_size=1 のため必ず1件
        record = event["Records"][0]
        message_body = json.loads(record["body"])
        album_url = message_body["album_url"]
        page = message_body["page"]
        base_url = message_body["base_url"]

        logger.info(f"Processing page {page} from {album_url}")

        # ページをスクレイプ（パスワード認証対応）
        page_url = f"{album_url}?page={page}"
        album_page_soup = _fetch_album_page(page_url, password=album_password)
        album_data = _extract_album_data(album_page_soup)

        # メディアをダウンロードしてS3に保存
        results = _download_media_files_to_s3(
            album_data,
            base_url,
            s3_bucket,
            s3_prefix=f"mitene-download/page-{page}",
        )

        logger.info(f"Page {page} completed: {results}")

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Page processed successfully",
                    "page": page,
                    "results": results,
                }
            ),
        }

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse SQS message: {str(e)}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Error in worker: {str(e)}", exc_info=True)
        raise
