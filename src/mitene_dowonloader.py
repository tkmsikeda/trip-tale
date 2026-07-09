import json
import os
import re
import time

import requests
from bs4 import BeautifulSoup
from datetime import datetime

dl_dir = "dl"
os.makedirs(dl_dir, exist_ok=True)


def _load_env_file() -> None:
    """.env ファイルから環境変数を読み込む"""
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".env",
    )
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()


def _make_filename(media_file: dict) -> str:
    """メディア情報からダウンロード先のファイル名を生成する"""
    captured_at = media_file["tookAt"]
    captured_at_datetime = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    timestamp_str = captured_at_datetime.strftime("%Y%m%d%H%M%S")
    extension = media_file["contentType"].split("/")[-1]
    return f"{timestamp_str}.{extension}"


def _make_download_url(media_file: dict, base_url: str) -> str:
    """メディア種別に応じて、ダウンロード先URLを返す"""
    if media_file.get("mediaType") == "movie":
        return f"{base_url}/media_files/{media_file['uuid']}/download"

    return media_file.get("expiringUrl") or (
        f"{base_url}/media_files/{media_file['uuid']}/download"
    )


def _find_gon_media_script_text(soup):
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


def _fetch_album_page(page_url: str) -> BeautifulSoup:
    """アルバムページのHTMLを取得して、BeautifulSoupオブジェクトを返す"""
    response = requests.get(page_url)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def _extract_album_data(soup: BeautifulSoup) -> dict:
    """アルバムページから、メディアダウンロードに必要なデータを抽出する"""
    json_string = _find_gon_media_script_text(soup)
    if not json_string:
        raise Exception("Could not find JavaScript variable 'gon'")
    return json.loads(json_string)


def _download_media_files(album_data: dict, base_url: str) -> None:
    """アルバムデータに基づいて、メディアをダウンロードする"""
    for media_file in album_data["mediaFiles"]:
        filename = _make_filename(media_file)
        file_path = os.path.join(dl_dir, filename)

        media_url = _make_download_url(media_file, base_url)

        response = requests.get(media_url)
        response.raise_for_status()
        if os.path.exists(file_path):
            base, ext = os.path.splitext(file_path)
            file_path = f"{base}_{media_file['uuid']}{ext}"

        with open(file_path, "wb") as f:
            f.write(response.content)

        time.sleep(1)


def save_files(album_url: str, page: int, end_page: int | None = None):
    """
    指定されたみてねURLのページから、メディアファイルをダウンロードして保存する
    """

    if page % 10 == 0:
        print(page)

    page_url = f"{album_url}?page={page}"
    album_page_soup = _fetch_album_page(page_url)
    album_data = _extract_album_data(album_page_soup)
    _download_media_files(album_data, album_url)

    # 次のページが存在する場合は再帰的に処理
    if album_data["hasNext"] and (end_page is None or page < end_page):
        save_files(album_url, page + 1, end_page)


if __name__ == "__main__":
    album_url = os.getenv("MITENE_ALBUM_URL")
    if not album_url:
        raise ValueError("MITENE_ALBUM_URL が設定されていません。 .env を確認してください。")

    save_files(album_url, 1, 12)  # 初回の呼び出し（end_page を指定で終了ページを制限可能）
