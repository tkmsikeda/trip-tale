import json
import logging
import os
import subprocess

import boto3

s3 = boto3.client("s3")
sqs = boto3.client("sqs")
dynamodb = boto3.resource("dynamodb")

# Environment Variables
TABLE_NAME = os.environ.get("TABLE_NAME")
QUEUE_URL_MERGE = os.environ.get("QUEUE_URL_MERGE")

if TABLE_NAME:
    dynamodb_table = dynamodb.Table(TABLE_NAME)
else:
    dynamodb_table = None

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def extract_job_info(event):
    """SQSイベントからjob_id, bucket, keyを取得する"""
    if not event.get("Records"):
        raise Exception("No Records found in event")

    record = event["Records"][0]

    # SQSメッセージボディをJSONとしてパース
    try:
        body = json.loads(record.get("body", "{}"))
    except json.JSONDecodeError as e:
        raise Exception(f"Failed to parse SQS message body: {e}")

    job_id = body.get("job_id")
    bucket = body.get("bucket")
    key = body.get("key")

    if not job_id or not bucket or not key:
        raise Exception("job_id, bucket, or key not found in SQS message")

    return job_id, bucket, key


def download_from_s3(bucket, key):
    """S3からファイルをダウンロードする

    Args:
        bucket: S3バケット名
        key: S3オブジェクトキー

    Returns:
        (download_path, download_size) のタプル
    """
    file_name = os.path.basename(key)
    download_path = f"/tmp/{file_name}"
    logger.info(
        "Downloading from S3. bucket=%s key=%s local_path=%s",
        bucket,
        key,
        download_path,
    )
    s3.download_file(bucket, key, download_path)

    if not os.path.exists(download_path):
        raise Exception(f"Downloaded file was not created: {download_path}")

    download_size = os.path.getsize(download_path)
    logger.info(
        "Download completed. local_path=%s size_bytes=%s",
        download_path,
        download_size,
    )

    return download_path, download_size


def format_video(input_path, output_path, fps):
    """FFmpegで動画をフォーマット処理する

    Args:
        input_path: 入力ファイルパス
        output_path: 出力ファイルパス
        fps: 出力FPS

    Returns:
        output_size: 出力ファイルサイズ
    """
    ffmpeg_cmd = build_ffmpeg_command(input_path, output_path, fps)
    logger.info("Running FFmpeg command: %s", ffmpeg_cmd)

    result = subprocess.run(
        ffmpeg_cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    logger.info("FFmpeg finished with return code: %s", result.returncode)
    if result.stdout.strip():
        logger.info("FFmpeg output:\n%s", result.stdout.strip())

    if result.returncode != 0:
        ffmpeg_output = result.stdout.strip()
        logger.error("FFmpeg processing failed. output=%s", ffmpeg_output)
        raise Exception(f"FFmpeg processing failed: {ffmpeg_output}")

    if not os.path.exists(output_path):
        raise Exception(f"FFmpeg did not create output file: {output_path}")

    output_size = os.path.getsize(output_path)
    logger.info(
        "FFmpeg output created. local_path=%s size_bytes=%s",
        output_path,
        output_size,
    )

    return output_size


def upload_to_s3(local_path, bucket, key):
    """S3にファイルをアップロードする

    Args:
        local_path: ローカルファイルパス
        bucket: S3バケット名
        key: S3オブジェクトキー
    """
    logger.info(
        "Uploading to S3. bucket=%s key=%s local_path=%s",
        bucket,
        key,
        local_path,
    )
    s3.upload_file(local_path, bucket, key)
    logger.info("Upload completed. s3://%s/%s", bucket, key)


def cleanup_temp_files(*file_paths):
    """一時ファイルを削除する

    Args:
        *file_paths: 削除するファイルパス
    """
    for file_path in file_paths:
        if os.path.exists(file_path):
            os.remove(file_path)
    logger.info("Cleanup completed")


def update_job_progress(job_id):
    """DynamoDBで completed_count をインクリメント

    Args:
        job_id: ジョブID

    Returns:
        更新後のジョブレコード
    """
    if not dynamodb_table:
        logger.warning("DynamoDB table not configured, skipping progress update")
        return None

    logger.info("Updating job progress. job_id=%s", job_id)
    response = dynamodb_table.update_item(
        Key={"job_id": job_id},
        UpdateExpression="ADD completed_count :inc",
        ExpressionAttributeValues={":inc": 1},
        ReturnValues="ALL_NEW",
    )

    updated_item = response.get("Attributes", {})
    logger.info(
        "Job progress updated",
        extra={
            "job_id": job_id,
            "completed_count": updated_item.get("completed_count"),
            "expected_count": updated_item.get("expected_count"),
        },
    )

    return updated_item


def check_and_finalize_job(job_id):
    """並列タスク全体の進捗確認し、すべて完了していれば最後のLambdaを起動

    Args:
        job_id: ジョブID

    Returns:
        bool: すべての処理が完了したか
    """
    if not dynamodb_table:
        logger.warning("DynamoDB table not configured, skipping finalization check")
        return False

    logger.info("Checking job completion status. job_id=%s", job_id)

    # 現在のジョブ情報を取得
    response = dynamodb_table.get_item(Key={"job_id": job_id})
    job_item = response.get("Item", {})

    expected_count = job_item.get("expected_count", 0)
    completed_count = job_item.get("completed_count", 0)

    logger.info(
        "Job completion status",
        extra={
            "job_id": job_id,
            "completed_count": completed_count,
            "expected_count": expected_count,
        },
    )

    # すべて完了したかチェック
    if completed_count >= expected_count:
        logger.info("All tasks completed. Finalizing job. job_id=%s", job_id)

        # DynamoDBのステータスを更新
        dynamodb_table.update_item(
            Key={"job_id": job_id},
            UpdateExpression="SET #status = :completed",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":completed": "COMPLETED"},
        )
        logger.info("Job status updated to COMPLETED. job_id=%s", job_id)

        # SQSに最後のLambdaをトリガーするメッセージを送信
        if QUEUE_URL_MERGE:
            message = {"job_id": job_id}
            logger.info("Sending merge trigger message to SQS. job_id=%s", job_id)
            sqs.send_message(QueueUrl=QUEUE_URL_MERGE, MessageBody=json.dumps(message))
            logger.info("Merge trigger message sent successfully. job_id=%s", job_id)
        else:
            logger.warning(
                "QUEUE_URL_MERGE not configured, skipping merge trigger. job_id=%s",
                job_id,
            )

        return True

    return False


def lambda_handler(event, context):
    """
    S3の動画を1つフォーマット処理する（SQSメッセージからトリガー）

    SQSメッセージボディ: {
        "job_id": "ba909eac-691d-42e6-93b8-682d7604204e",
        "bucket": "home-video-original",
        "key": "20260702-1458.mp4"
    }
    """
    try:
        logger.info(f"Starting video formatting for event: {json.dumps(event)}")

        # SQSメッセージからジョブ情報を抽出
        job_id, bucket, key = extract_job_info(event)

        # S3からダウンロード
        download_path, download_size = download_from_s3(bucket, key)
        file_name = os.path.basename(key)

        # 動画から FPS を取得
        original_fps = get_video_fps(download_path)
        output_fps = normalize_fps(original_fps)
        logger.info(
            "Processing video: s3://%s/%s original_fps=%s output_fps=%s",
            bucket,
            key,
            original_fps,
            output_fps,
        )

        # 動画をフォーマット処理
        output_file = f"formatted_{file_name}"
        output_path = f"/tmp/{output_file}"
        logger.info("Output path will be %s", output_path)
        format_video(download_path, output_path, output_fps)

        # 出力先バケットを環境変数から取得
        output_bucket = os.environ.get("OUTPUT_BUCKET")
        if not output_bucket:
            raise Exception("OUTPUT_BUCKET environment variable is not set")

        # S3にアップロード
        output_key = f"formatted/{output_file}"
        upload_to_s3(output_path, output_bucket, output_key)

        # クリーンアップ
        cleanup_temp_files(download_path, output_path)

        # ジョブ進捗を更新
        update_job_progress(job_id)

        # すべてのタスクが完了したかチェック
        all_completed = check_and_finalize_job(job_id)

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "status": "success",
                    "job_id": job_id,
                    "output_key": output_key,
                    "input_key": key,
                    "all_tasks_completed": all_completed,
                }
            ),
        }

    except Exception as e:
        logger.exception("Error during video formatting")
        return {
            "statusCode": 500,
            "body": json.dumps({"status": "error", "message": str(e)}),
        }


def get_video_fps(input_path):
    """動画ファイルから FPS を取得する"""
    logger.info("Running ffprobe for %s", input_path)
    ffprobe_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=r_frame_rate",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        input_path,
    ]
    result = subprocess.run(
        ffprobe_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        logger.error(
            "ffprobe failed. input_path=%s stderr=%s", input_path, result.stderr
        )
        raise Exception(f"Failed to read video FPS: {result.stderr}")

    fps_str = result.stdout.strip()
    logger.info("ffprobe completed. input_path=%s fps_raw=%s", input_path, fps_str)
    if not fps_str:
        raise Exception("ffprobe did not return an FPS value")

    if "/" in fps_str:
        numerator, denominator = fps_str.split("/")
        fps = float(numerator) / float(denominator)
    else:
        fps = float(fps_str)

    return round(fps, 2)


def normalize_fps(fps):
    """実際のFPSに応じて出力FPSを決定する"""
    if fps in (30.0, 60.0):
        return fps
    if fps == 29.97:
        return 30.0
    if fps == 59.94:
        return 60.0
    return 30.0


def build_ffmpeg_command(input_path, output_path, fps):
    """
    FFmpegコマンドを生成
    - 1920x1080に変換（アスペクト比維持 + 黒枠）
    - FPS統一
    """
    return (
        f"ffmpeg -loglevel error -i {input_path} "
        f'-vf "scale=1920:1080:force_original_aspect_ratio=decrease,'
        f'pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps={fps}" '
        f"-c:v libx264 -pix_fmt yuv420p "
        f"-c:a aac -ar 44100 -ac 2 -b:a 128k "
        f"{output_path}"
    )
