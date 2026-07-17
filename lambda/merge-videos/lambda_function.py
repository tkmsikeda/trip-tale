import json
import subprocess
import boto3
import os
import logging

s3 = boto3.client("s3")
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def list_video_keys(bucket_name):
    paginator = s3.get_paginator("list_objects_v2")
    page_iterator = paginator.paginate(Bucket=bucket_name)
    keys = []
    video_exts = (".mov", ".mp4", ".mkv", ".avi", ".mov", ".wmv")
    for page in page_iterator:
        for obj in page.get("Contents", []):
            key = obj.get("Key")
            if key and key.lower().endswith(video_exts):
                keys.append(key)
    return sorted(keys)


def create_concat_file(file_list):
    """ffmpeg concat用ファイルを生成"""
    concat_path = "/tmp/concat_list.txt"
    with open(concat_path, "w", encoding="utf-8") as f:
        for file_path in file_list:
            # ffmpegのpath指定では シングルクォートで囲む
            f.write(f"file '{file_path}'\n")
    return concat_path


def reorder_file_list(file_list, keyword="slideshow"):
    """basename に `keyword` を含むファイルを末尾へ移動し、元の相対順序を保持します。

    パスの basename を大文字小文字を区別せずに検索します。
    """
    keyword_l = keyword.lower()
    slides = [p for p in file_list if keyword_l in os.path.basename(p).lower()]
    others = [p for p in file_list if keyword_l not in os.path.basename(p).lower()]
    return others + slides


def update_job_in_dynamodb(job_id, output_key):
    """`job_id` を使って DynamoDB のジョブレコードを更新する。

    環境変数 `TABLE_NAME` が未設定の場合はスキップする。
    """
    TABLE_NAME = os.environ.get("TABLE_NAME")
    if not TABLE_NAME:
        logger.info("TABLE_NAME not set; skipping DynamoDB update")
        return

    if not job_id:
        logger.info("No job_id provided; skipping DynamoDB update")
        return

    try:
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(TABLE_NAME)

        table.update_item(
            Key={"job_id": job_id},
            UpdateExpression="SET merge_output_key = :k, #st = :s",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={":k": output_key, ":s": "MERGED"},
        )
        logger.info(f"DynamoDB updated for job_id={job_id}")
    except Exception as e:
        logger.error(f"Failed to update DynamoDB: {e}")


def lambda_handler(event, context):
    """
    S3にあるフォーマット済み動画を結合する

    event: SQSからのメッセージで、以下の構造:
        {
            "Records": [
                {
                    "body": '{"job_id": "..."}'
                }
            ]
        }
    """
    try:

        bucket = os.environ.get("BUCKET_NAME")
        if not bucket:
            raise Exception("環境変数 BUCKET_NAME が設定されていません。")

        # バケット内の全ての動画ファイルを列挙して対象とする。
        formatted_keys = list_video_keys(bucket)

        logger.info(f"Merging {len(formatted_keys)} videos from s3://{bucket}/")

        # 各動画をS3からダウンロード
        file_list = []
        for i, key in enumerate(sorted(formatted_keys)):
            file_name = os.path.basename(key)
            local_path = f"/tmp/{i}_{file_name}"
            logger.info(f"Downloading: {key}")
            s3.download_file(bucket, key, local_path)
            file_list.append(local_path)

        # ffmpeg concat用ファイルを生成（slideshow を末尾に移動）
        file_list = reorder_file_list(file_list, keyword="slideshow")
        logger.info("Reordered file_list to move slideshow files to the end")
        concat_file = create_concat_file(file_list)
        logger.info(f"Created concat file: {concat_file}")

        # 動画を結合
        output_path = "/tmp/final_video.MOV"
        ffmpeg_cmd = f'ffmpeg -loglevel error -f concat -safe 0 -i "{concat_file}" -c copy "{output_path}"'
        logger.info(f"Running FFmpeg merge: {ffmpeg_cmd}")

        result = subprocess.run(
            ffmpeg_cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            logger.error(f"FFmpeg merge error: {result.stderr}")
            raise Exception(f"FFmpeg merge failed: {result.stderr}")

        # S3にアップロード
        output_key = "output/final_video.MOV"
        logger.info(f"Uploading final video to S3: s3://{bucket}/{output_key}")
        s3.upload_file(output_path, bucket, output_key)

        # SQSから送られてくる job_id を抽出し、DynamoDB 更新を呼び出す
        job_id = json.loads(event["Records"][0]["body"])["job_id"]
        update_job_in_dynamodb(job_id, output_key)

        # クリーンアップ
        for file_path in file_list:
            os.remove(file_path)
        os.remove(concat_file)
        os.remove(output_path)
        logger.info("Cleanup completed")

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "status": "success",
                    "output_key": output_key,
                    "merged_count": len(file_list),
                }
            ),
        }

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"status": "error", "message": str(e)}),
        }
