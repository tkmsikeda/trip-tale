import json
import logging
import os
from datetime import datetime

import boto3

logger = logging.getLogger()
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logger.setLevel(log_level)

sqs = boto3.client("sqs")


def _create_page_messages(
    album_url: str,
    pages_to_process: int,
    target_start_at: str,
    target_end_at: str,
) -> list:
    """
    指定されたページ数分の独立したSQSメッセージを生成

    各メッセージは1ページのダウンロード処理に対応

    Args:
        album_url (str): アルバムのURL
        pages_to_process (int): 生成対象のページ数
        target_start_at (str): 対象期間の開始日時（ISO 8601形式）
        target_end_at (str): 対象期間の終了日時（ISO 8601形式、排他的）

    Returns:
        list: SQS send_message_batch 用のメッセージエントリリスト
              各エントリは {"Id": str, "MessageBody": json_str} 形式

    例: pages_to_process=12 の場合
      - Message 1: {"page": 1, "album_url": "..."}
      - Message 2: {"page": 2, "album_url": "..."}
      - ...
      - Message 12: {"page": 12, "album_url": "..."}
    """
    entries = []

    for page in range(1, pages_to_process + 1):
        message = {
            "album_url": album_url,
            "page": page,
            "base_url": album_url,
            "target_start_at": target_start_at,
            "target_end_at": target_end_at,
        }

        entries.append(
            {
                "Id": str(page),
                "MessageBody": json.dumps(message),
            }
        )

    logger.info(f"Created {len(entries)} SQS messages (one per page)")
    return entries


def _send_messages_to_sqs(
    queue_url: str,
    album_url: str,
    pages_to_process: int,
    target_start_at: str,
    target_end_at: str,
) -> None:
    """SQS キューにページ情報を送信する

    Args:
        queue_url (str): SQSキューのURL
        album_url (str): アルバムのURL
        pages_to_process (int): 送信対象のページ数
        target_start_at (str): 対象期間の開始日時（ISO 8601形式）
        target_end_at (str): 対象期間の終了日時（ISO 8601形式、排他的）

    Returns:
        None

    Raises:
        Exception: SQSメッセージ送信失敗時
    """
    logger.info(f"Sending messages to SQS queue: {queue_url}")
    entries = _create_page_messages(
        album_url, pages_to_process, target_start_at, target_end_at
    )

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
        END_PAGE (int): 処理対象の終了ページ（必須）
        TARGET_START_AT (str): 対象期間の開始日時（ISO 8601形式、必須）
        TARGET_END_AT (str): 対象期間の終了日時（ISO 8601形式、排他的、必須）

    Returns:
        dict: Lambda実行結果
    """
    timestamp = datetime.now().isoformat()
    logger.info(f"[mitene-orchestrator] Starting Lambda handler at {timestamp}")

    try:
        # 環境変数を取得
        album_url = os.getenv("MITENE_ALBUM_URL")
        queue_url = os.getenv("SQS_QUEUE_URL")
        end_page_text = os.getenv("END_PAGE")
        target_start_at = os.getenv("TARGET_START_AT")
        target_end_at = os.getenv("TARGET_END_AT")

        # 環境変数の検証
        logger.info("Environment variables check:")
        logger.info(f"  MITENE_ALBUM_URL: {'SET' if album_url else 'NOT SET'}")
        logger.info(f"  SQS_QUEUE_URL: {'SET' if queue_url else 'NOT SET'}")
        logger.info(f"  END_PAGE: {'SET' if end_page_text else 'NOT SET'}")
        logger.info(f"  TARGET_START_AT: {'SET' if target_start_at else 'NOT SET'}")
        logger.info(f"  TARGET_END_AT: {'SET' if target_end_at else 'NOT SET'}")

        if not album_url:
            raise ValueError("MITENE_ALBUM_URL is not set")
        if not queue_url:
            raise ValueError("SQS_QUEUE_URL is not set")
        if not end_page_text:
            raise ValueError("END_PAGE is not set")
        if not target_start_at:
            raise ValueError("TARGET_START_AT is not set")
        if not target_end_at:
            raise ValueError("TARGET_END_AT is not set")

        try:
            pages_to_process = int(end_page_text)
        except ValueError as exc:
            raise ValueError("END_PAGE must be an integer") from exc
        if pages_to_process < 1:
            raise ValueError("END_PAGE must be greater than or equal to 1")

        start_datetime = datetime.fromisoformat(
            target_start_at.replace("Z", "+00:00")
        )
        end_datetime = datetime.fromisoformat(target_end_at.replace("Z", "+00:00"))
        if start_datetime.tzinfo is None or end_datetime.tzinfo is None:
            raise ValueError("Target period must include a timezone")
        if start_datetime >= end_datetime:
            raise ValueError("TARGET_START_AT must be before TARGET_END_AT")

        logger.info(f"[Step 1/2] Starting orchestration for album: {album_url}")

        logger.info(f"[Step 1/2] Pages to process: 1-{pages_to_process}")

        # SQSにメッセージを送信
        logger.info(f"[Step 2/2] Sending {pages_to_process} messages to SQS...")
        _send_messages_to_sqs(
            queue_url,
            album_url,
            pages_to_process,
            target_start_at,
            target_end_at,
        )
        logger.info("[Step 2/2] ✓ All messages sent to SQS")

        logger.info(
            f"[SUCCESS] Orchestration completed. Pages sent: {pages_to_process}"
        )

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Orchestration completed",
                    "pages_to_process": pages_to_process,
                    "messages_sent": pages_to_process,
                }
            ),
        }

    except Exception as e:
        logger.error(f"[FAILED] Error in orchestrator: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }
