import json
import logging
import os
import uuid
from datetime import datetime

import boto3

# AWS Clients
s3 = boto3.client("s3")
sqs = boto3.client("sqs")
dynamodb = boto3.resource("dynamodb")

# Environment Variables
BUCKET_NAME = os.environ["BUCKET_NAME"]
PREFIX = os.environ.get("PREFIX", "")
QUEUE_URL = os.environ["QUEUE_URL"]
TABLE_NAME = os.environ["TABLE_NAME"]

dynamodb_table = dynamodb.Table(TABLE_NAME)

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def list_s3_object_keys(bucket, prefix):
    logger.info("Listing S3 object keys", extra={"bucket": bucket, "prefix": prefix})

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


def create_job_record(job_id, expected_count):
    logger.info(
        "Creating DynamoDB job record",
        extra={"job_id": job_id, "expected_count": expected_count},
    )
    dynamodb_table.put_item(
        Item={
            "job_id": job_id,
            "expected_count": expected_count,
            "completed_count": 0,
            "status": "PROCESSING",
            "created_at": datetime.utcnow().isoformat(),
        }
    )


def enqueue_sqs_messages(job_id, bucket, object_keys):
    logger.info(
        "Enqueuing SQS messages",
        extra={"job_id": job_id, "bucket": bucket, "message_count": len(object_keys)},
    )

    for key in object_keys:
        message = {"job_id": job_id, "bucket": bucket, "key": key}
        sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(message))


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

        # DynamoDBにジョブの進捗状況を登録
        create_job_record(job_id, object_count)

        # SQSにジョブを登録して、後続の前処理Lambdaを起動
        enqueue_sqs_messages(job_id, bucket, object_keys)

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
