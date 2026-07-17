import json
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3


def get_s3_client():
    return boto3.client("s3")


def get_sqs_client():
    return boto3.client("sqs")


def get_dynamodb_resource():
    return boto3.resource("dynamodb")


# Environment Variables
BUCKET_NAME = os.environ.get("BUCKET_NAME", "")
PREFIX = os.environ.get("PREFIX", "")
QUEUE_URL = os.environ.get("QUEUE_URL", "")
QUEUE_URL_SLIDESHOW = os.environ.get("QUEUE_URL_SLIDESHOW", "")
TABLE_NAME = os.environ.get("TABLE_NAME", "")
SLIDESHOW_AUDIO_KEY = os.environ.get("SLIDESHOW_AUDIO_KEY", "audio.mp3")

try:
    dynamodb = get_dynamodb_resource()
    dynamodb_table = dynamodb.Table(TABLE_NAME) if TABLE_NAME else None
except Exception:
    dynamodb = None
    dynamodb_table = None

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def list_s3_object_keys(bucket, prefix):
    logger.info("Listing S3 object keys", extra={"bucket": bucket, "prefix": prefix})

    s3 = get_s3_client()
    object_keys = []
    paginator = s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]

            # フォルダ除外
            if key.endswith("/"):
                continue

            object_keys.append(key)

    logger.info("Found S3 object keys", extra={"count": len(object_keys)})
    return object_keys


def create_job_record(job_id, expected_count, audio_key=None):
    logger.info(
        "Creating DynamoDB job record",
        extra={"job_id": job_id, "expected_count": expected_count},
    )
    item = {
        "job_id": job_id,
        "expected_count": expected_count,
        "completed_count": 0,
        "status": "PROCESSING",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if audio_key is not None:
        item["slideshow_audio_key"] = audio_key
        item["slideshow_status"] = "PENDING"
        item["slideshow_output_key"] = None
    dynamodb_table.put_item(Item=item)


def enqueue_sqs_messages(job_id, bucket, object_keys):
    logger.info(
        "Enqueuing SQS messages",
        extra={"job_id": job_id, "bucket": bucket, "message_count": len(object_keys)},
    )

    sqs = get_sqs_client()
    for key in object_keys:
        message = {"job_id": job_id, "bucket": bucket, "key": key}
        sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(message))


def enqueue_slideshow_job(job_id, bucket, audio_key=None):
    if not job_id:
        logger.info("No job_id provided; skipping slideshow enqueue")
        return

    if not QUEUE_URL_SLIDESHOW:
        logger.warning("QUEUE_URL_SLIDESHOW not configured; skipping slideshow enqueue")
        return

    sqs = get_sqs_client()
    message = {"job_id": job_id, "bucket": bucket, "audio_key": audio_key}
    logger.info(
        "Sending slideshow job to SQS",
        extra={
            "queue_url": QUEUE_URL_SLIDESHOW,
            "job_id": job_id,
            "bucket": bucket,
            "audio_key": audio_key,
        },
    )
    sqs.send_message(QueueUrl=QUEUE_URL_SLIDESHOW, MessageBody=json.dumps(message))
    logger.info("Slideshow job enqueued successfully", extra={"job_id": job_id})


def lambda_handler(_event, _context):
    """
    目的: 動画の前処理用の後続のLambdaを動かす際に、
    すべての動画を前処理できたかを判断するための進捗管理用の仕組みを用意すること
    概要: S3からファイル名一覧を取得し、SQSに登録することで後続の前処理Lambdaを起動する。
    また、DynamoDBにジョブの進捗状況を登録することで、すべての動画が前処理できたかを
    後続の前処理Lambdaで判断することができる。
    必要なインプット: なし
    """

    bucket = BUCKET_NAME
    prefix = PREFIX

    try:
        logger.info(
            "Lambda handler started", extra={"bucket": bucket, "prefix": prefix}
        )

        # S3からオブジェクトキー一覧を取得
        object_keys = list_s3_object_keys(bucket, prefix)
        if not object_keys:
            logger.info(
                "No S3 objects found", extra={"bucket": bucket, "prefix": prefix}
            )
            return {"statusCode": 200, "body": "No files."}

        job_id = str(uuid.uuid4())
        object_count = len(object_keys)
        slideshow_audio_key = SLIDESHOW_AUDIO_KEY

        # DynamoDBにジョブの進捗状況を登録
        create_job_record(job_id, object_count, audio_key=slideshow_audio_key)

        # SQSにジョブを登録して、後続の前処理Lambdaを起動
        enqueue_sqs_messages(job_id, bucket, object_keys)
        enqueue_slideshow_job(job_id, bucket, audio_key=slideshow_audio_key)

        logger.info(
            "Lambda handler completed successfully",
            extra={"job_id": job_id, "file_count": object_count},
        )
        return {
            "statusCode": 200,
            "body": json.dumps({"job_id": job_id, "file_count": object_count}),
        }
    except Exception as exc:
        logger.exception("S3 preparer failed")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(exc)}),
        }
