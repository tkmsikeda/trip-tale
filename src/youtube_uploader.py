import os

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# 認証情報のファイルパス
CLIENT_SECRETS_FILE = "client_secret.json"
# 必要なスコープ（動画のアップロード権限）
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# APIサービス名とバージョン
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"


# トークン保存ファイル名を固定
TOKEN_FILE = "token.json"


def get_authenticated_service() -> object:
    """
    認証情報をロードまたは新規取得（必要に応じてリフレッシュ）し、
    YouTube Data APIの認証済みサービスオブジェクト（APIクライアント）を返す。
    """
    credentials = (
        Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if os.path.exists(TOKEN_FILE)
        else None
    )
    is_credentials_valid, can_refresh_credentials = check_credentials(credentials)

    if is_credentials_valid:
        return build(API_SERVICE_NAME, API_VERSION, credentials=credentials)

    if can_refresh_credentials:
        credentials.refresh(Request())
        save_token(credentials)
        return build(API_SERVICE_NAME, API_VERSION, credentials=credentials)

    # 認証情報なし、またはリフレッシュ不可 → ブラウザ認証
    credentials = authorize_via_browser()

    return build(API_SERVICE_NAME, API_VERSION, credentials=credentials)


def check_credentials(credentials) -> tuple[bool, bool]:
    """
    認証情報を判定
    Returns:
        is_valid (bool): 認証情報が有効か
        can_refresh (bool): リフレッシュ可能か
    """
    is_valid = credentials and credentials.valid
    can_refresh = credentials and credentials.expired and credentials.refresh_token
    return is_valid, can_refresh


def save_token(credentials) -> None:
    """認証情報を token.json に保存"""
    with open(TOKEN_FILE, "w") as f:
        f.write(credentials.to_json())


def authorize_via_browser() -> Credentials:
    """ブラウザ認証を行い、新しい認証情報を取得して保存"""
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
    # flow.run_console() または flow.run_local_server(port=0) を実行
    # ※ run_console()を使う場合は、クライアントIDの設定でリダイレクトURIが削除されていることを確認
    credentials = flow.run_local_server(port=0)  # ローカルサーバーフローを使用
    save_token(credentials)
    return credentials


def upload_video(
    youtube, file_path, title, description, tags, category_id, privacy_status
):
    # 動画のメタデータ（videoリソースのbody）
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
        },
    }

    # 再開可能なアップロードのための MediaFileUpload
    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)

    # videos().insert() メソッドの呼び出し
    request = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media
    )

    response = None
    print("アップロードを開始します...")

    # 再開可能なアップロードの進行
    while response is None:
        status, response = request.next_chunk()
        if status:
            # 進捗状況を表示
            print(f"Uploaded {int(status.progress() * 100)}%")

    print("アップロードが完了しました！")
    # 完了後のレスポンス（動画リソース）
    if "id" in response:
        print(f"動画ID: {response['id']}")
        print(f"動画URL: https://youtu.be/{response['id']}")
    else:
        print("予期せぬレスポンスでアップロードに失敗しました。")

    return response


# --- 実行例 ---
def main():
    # 認証されたAPIサービスを取得
    youtube = get_authenticated_service()

    # アップロードする動画の情報
    VIDEO_FILE = "./final_video.MOV"  # 実際は動画ファイルのパスに置き換えてください
    VIDEO_TITLE = "20251122-マリフェス"
    VIDEO_DESCRIPTION = "20251122-マリフェス"
    VIDEO_TAGS = ["Python", "YouTube API", "テスト"]
    CATEGORY_ID = "22"  # 22は "People & Blogs"
    PRIVACY_STATUS = "unlisted"  # 'public', 'private', 'unlisted'

    # 動画をアップロード
    if os.path.exists(VIDEO_FILE):
        upload_video(
            youtube,
            VIDEO_FILE,
            VIDEO_TITLE,
            VIDEO_DESCRIPTION,
            VIDEO_TAGS,
            CATEGORY_ID,
            PRIVACY_STATUS,
        )
    else:
        print(f"エラー: ファイルが見つかりません - {VIDEO_FILE}")
