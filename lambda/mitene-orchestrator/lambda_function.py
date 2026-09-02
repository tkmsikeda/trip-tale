import json
import logging
import os
import re

import boto3
from bs4 import BeautifulSoup
import requests
from datetime import datetime

logger = logging.getLogger()
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logger.setLevel(log_level)

sqs = boto3.client("sqs")


def _fetch_album_page(page_url: str, password: str | None = None) -> BeautifulSoup:
    """アルバムページのHTMLを取得して、BeautifulSoupオブジェクトを返す

    Args:
        page_url (str): アルバムページのURL
        password (str | None): みてねアルバムのパスワード（オプション）
                               未指定の場合はパスワード不要のアルバムとして処理

    Returns:
        BeautifulSoup: パースされたHTMLオブジェクト

    Raises:
        requests.exceptions.HTTPError: HTTPリクエスト失敗時
    """
    params = {"password": password} if password else {}
    logger.debug(f"Fetching album page: {page_url}")
    response = requests.get(page_url, params=params)
    logger.debug(f"HTTP status: {response.status_code}")
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def _find_gon_media_script_text(soup: BeautifulSoup) -> str | None:
    """JavaScript の gon.media オブジェクトを抽出

    Args:
        soup (BeautifulSoup): HTMLパース済みオブジェクト

    Returns:
        str | None: gon.media オブジェクトのJSON文字列
                    見つからない場合は None
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


def _extract_album_data(soup: BeautifulSoup) -> dict:
    """アルバムページから、メディアダウンロードに必要なデータを抽出する

    Args:
        soup (BeautifulSoup): HTMLパース済みオブジェクト

    Returns:
        dict: gon.media オブジェクトのパース済み辞書
              mediaFiles, hasNext, 等のキーを含む

    Raises:
        Exception: gon.media が見つからない場合
    """
    json_string = _find_gon_media_script_text(soup)
    if not json_string:
        logger.error("Could not find gon.media in script tags")
        raise Exception("Could not find JavaScript variable 'gon'")
    data = json.loads(json_string)
    logger.debug(f"Extracted album data: {len(data.get('mediaFiles', []))} media files")
    return data


def _get_total_pages(
    album_url: str, end_page: int | None = None, password: str | None = None
) -> int:
    """総ページ数を取得する

    Args:
        album_url (str): アルバムのベースURL
        end_page (int | None): 終了ページ（指定時は処理対象の上限）
        password (str | None): みてねアルバムのパスワード（オプション）

    Returns:
        int: アルバムの総ページ数

    Raises:
        Exception: gon.media が見つからない場合
    """
    page = 1
    total_pages = 1

    while True:
        logger.info(f"Checking page {page}...")
        page_url = f"{album_url}?page={page}"
        album_page_soup = _fetch_album_page(page_url, password)
        album_data = _extract_album_data(album_page_soup)

        if not album_data.get("hasNext"):
            total_pages = page
            logger.info(f"Reached last page: {total_pages}")
            break

        if end_page and page >= end_page:
            total_pages = page
            logger.info(f"Reached end_page limit: {total_pages}")
            break

        page += 1

    logger.info(f"Total pages: {total_pages}")
    return total_pages


def _create_page_messages(album_url: str, total_pages: int) -> list:
    """
    Orchestrator: total_pages分の独立したSQSメッセージを生成

    各メッセージは1ページのダウンロード処理に対応

    Args:
        album_url (str): アルバムのURL
        total_pages (int): 生成対象のページ数

    Returns:
        list: SQS send_message_batch 用のメッセージエントリリスト
              各エントリは {"Id": str, "MessageBody": json_str} 形式

    例: total_pages=12 の場合
      - Message 1: {"page": 1, "album_url": "..."}
      - Message 2: {"page": 2, "album_url": "..."}
      - ...
      - Message 12: {"page": 12, "album_url": "..."}
    """
    entries = []

    for page in range(1, total_pages + 1):
        message = {
            "album_url": album_url,
            "page": page,
            "base_url": album_url,
        }

        entries.append(
            {
                "Id": str(page),
                "MessageBody": json.dumps(message),
            }
        )

    logger.info(f"Created {len(entries)} SQS messages (one per page)")
    return entries


def _send_messages_to_sqs(queue_url: str, album_url: str, total_pages: int) -> None:
    """SQS キューにページ情報を送信する

    Args:
        queue_url (str): SQSキューのURL
        album_url (str): アルバムのURL
        total_pages (int): 送信対象のページ数

    Returns:
        None

    Raises:
        Exception: SQSメッセージ送信失敗時
    """
    # total_pages分の独立したメッセージを生成（1メッセージ = 1ページ）
    logger.info(f"Sending messages to SQS queue: {queue_url}")
    entries = _create_page_messages(album_url, total_pages)

    # SQS API の制限により最大10個ずつに分割して送信
    for i in range(0, len(entries), 10):
        batch = entries[i : i + 10]
        logger.debug(f"Sending batch: pages {batch[0]['Id']}-{batch[-1]['Id']}")
        response = sqs.send_message_batch(QueueUrl=queue_url, Entries=batch)

        if response.get("Failed"):
            logger.error(f"Failed to send messages: {response['Failed']}")
            raise Exception("Failed to send SQS messages")

        msg = (
            f"Successfully sent {len(batch)} messages to SQS "
            f"(pages {batch[0]['Id']}-{batch[-1]['Id']})"
        )
        logger.info(msg)


def lambda_handler(event, context):
    """
    オーケストレータLambda
    - アルバムURLからページ数を取得
    - SQSキューにメッセージを送信

    環境変数:
        MITENE_ALBUM_URL (str): みてねアルバムのURL（必須）
        SQS_QUEUE_URL (str): SQSキューのURL（必須）
        MITENE_ALBUM_PASSWORD (str): アルバムパスワード（オプション）
        END_PAGE (int): 処理対象の終了ページ（デフォルト: 全ページ）

    Returns:
        dict: Lambda実行結果
    """
    timestamp = datetime.now().isoformat()
    logger.info(f"[mitene-orchestrator] Starting Lambda handler at {timestamp}")

    try:
        # 環境変数を取得
        album_url = os.getenv("MITENE_ALBUM_URL")
        queue_url = os.getenv("SQS_QUEUE_URL")
        password = os.getenv("MITENE_ALBUM_PASSWORD")
        end_page = int(os.getenv("END_PAGE", "0")) or None

        # 環境変数の検証
        logger.info("Environment variables check:")
        logger.info(f"  MITENE_ALBUM_URL: {'SET' if album_url else 'NOT SET'}")
        logger.info(f"  SQS_QUEUE_URL: {'SET' if queue_url else 'NOT SET'}")
        logger.info(f"  MITENE_ALBUM_PASSWORD: {'SET' if password else 'NOT SET'}")
        logger.info(f"  END_PAGE: {end_page}")

        if not album_url:
            raise ValueError("MITENE_ALBUM_URL is not set")
        if not queue_url:
            raise ValueError("SQS_QUEUE_URL is not set")

        logger.info(f"[Step 1/2] Starting orchestration for album: {album_url}")

        # 総ページ数を取得
        total_pages = _get_total_pages(album_url, end_page, password)
        logger.info(f"[Step 1/2] ✓ Detected total pages: {total_pages}")

        # SQSにメッセージを送信
        logger.info(f"[Step 2/2] Sending {total_pages} messages to SQS...")
        _send_messages_to_sqs(queue_url, album_url, total_pages)
        logger.info("[Step 2/2] ✓ All messages sent to SQS")

        logger.info(f"[SUCCESS] Orchestration completed. Total pages: {total_pages}")

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Orchestration completed",
                    "total_pages": total_pages,
                    "messages_sent": total_pages,
                }
            ),
        }

    except Exception as e:
        logger.error(f"[FAILED] Error in orchestrator: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }
