import json
import subprocess
import boto3
import os
import logging
from PIL import Image, ExifTags

_s3_client = None


def get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


def get_sqs_client():
    return boto3.client("sqs")


logger = logging.getLogger()
logger.setLevel(logging.INFO)
QUEUE_URL_FORMAT_VIDEO = os.environ.get("QUEUE_URL_FORMAT_VIDEO")

DURATION_PER_IMAGE_SECONDS = 5
FFMPEG_LIST_FILE = "/tmp/image_files.txt"
OUTPUT_VIDEO = "/tmp/output.MOV"
FINAL_VIDEO = "/tmp/image_audio_video.MOV"


def build_output_key(job_id: str | None) -> str:
    """S3 バケット直下に保存する出力キーを生成する。"""
    job_name = job_id if job_id else "default"
    return f"slideshow_{job_name}.MOV"


def list_image_keys(bucket_name, s3_client=None):
    """S3バケット内の画像ファイルを取得"""
    s3 = s3_client or get_s3_client()
    paginator = s3.get_paginator("list_objects_v2")
    page_iterator = paginator.paginate(Bucket=bucket_name)
    keys = []
    image_exts = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp")
    for page in page_iterator:
        for obj in page.get("Contents", []):
            key = obj.get("Key")
            if key and key.lower().endswith(image_exts):
                keys.append(key)
    return sorted(keys)


def get_image_orientation(image_path: str) -> int:
    """
    画像の回転情報を取得する関数
    :param image_path: 画像のパス
    :return: 回転情報
    """
    try:
        with Image.open(image_path) as img:
            exif = img._getexif()

        default_orientation = 1
        if exif is None:
            return default_orientation

        tagname_value_map = {}
        for tag_id, value in exif.items():
            tag_name = ExifTags.TAGS.get(tag_id, tag_id)
            tagname_value_map[tag_name] = value

        orientation = tagname_value_map.get("Orientation", default_orientation)
        logger.info(f"orientation of {image_path}: {orientation}")
        return orientation
    except Exception as e:
        logger.warning(f"Failed to get orientation for {image_path}: {e}")
        return 1


def rotate_image(image_path: str) -> str:
    """
    画像を回転させ、回転情報を除去する
    :param image_path: 元の画像パス
    :return: 回転後のファイルパス（または元のパス）
    """
    orientation = get_image_orientation(image_path)

    # 回転マッピング
    rotation_map = {
        2: Image.Transpose.FLIP_LEFT_RIGHT,
        3: Image.Transpose.ROTATE_180,
        4: Image.Transpose.FLIP_TOP_BOTTOM,
        5: Image.Transpose.TRANSPOSE,
        6: Image.Transpose.ROTATE_270,
        7: Image.Transpose.TRANSVERSE,
        8: Image.Transpose.ROTATE_90,
    }

    if orientation == 1:
        logger.info(f"No rotation needed for {image_path}")
        return image_path

    try:
        with Image.open(image_path) as img:
            if orientation in rotation_map:
                img = img.transpose(rotation_map[orientation])

            rotated_path = f"/tmp/rotated_{os.path.basename(image_path)}"

            # 回転情報を削除してセーブ
            if "exif" in img.info:
                img.info.pop("exif")
            img.save(rotated_path)

            logger.info(f"Image rotated and saved: {rotated_path}")
            return rotated_path
    except Exception as e:
        logger.error(f"Failed to rotate image {image_path}: {e}")
        return image_path


def create_concat_file(file_list):
    """ffmpeg concat用ファイルを生成"""
    with open(FFMPEG_LIST_FILE, "w", encoding="utf-8") as f:
        for file_path in file_list:
            f.write(f"file '{file_path}'\n")
            f.write(f"duration {DURATION_PER_IMAGE_SECONDS}\n")

        # ffmpegの仕様で最後のファイルを2度書かないと表示してくれないので、追記。
        f.write(f"file '{file_list[-1]}'")

    logger.info(f"Created concat file: {FFMPEG_LIST_FILE}")
    return FFMPEG_LIST_FILE


def images_to_video():
    """画像を動画に変換"""
    ffmpeg_cmd = f'ffmpeg -loglevel error -f concat -safe 0 -i "{FFMPEG_LIST_FILE}" -vsync vfr -vcodec libx264 -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2" -pix_fmt yuv420p "{OUTPUT_VIDEO}"'
    logger.info(f"Running FFmpeg convert images to video: {ffmpeg_cmd}")

    result = subprocess.run(
        ffmpeg_cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        logger.error(f"FFmpeg convert images error: {result.stderr}")
        raise Exception(f"FFmpeg convert images failed: {result.stderr}")


def add_audio_to_video(audio_path: str):
    """動画に音声を追加"""
    ffmpeg_cmd = f'ffmpeg -loglevel error -stream_loop -1 -i "{audio_path}" -i "{OUTPUT_VIDEO}" -c:v copy -c:a aac -af "volume=0.5" -shortest "{FINAL_VIDEO}"'
    logger.info(f"Running FFmpeg add audio to video: {ffmpeg_cmd}")

    result = subprocess.run(
        ffmpeg_cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        logger.error(f"FFmpeg add audio error: {result.stderr}")
        raise Exception(f"FFmpeg add audio failed: {result.stderr}")


def download_audio_from_s3(bucket_name: str, audio_key: str, s3_client=None):
    """S3から音声ファイルをダウンロード"""
    s3 = s3_client or get_s3_client()
    audio_path = f"/tmp/{os.path.basename(audio_key)}"
    logger.info(f"Downloading audio: {audio_key}")
    s3.download_file(bucket_name, audio_key, audio_path)
    return audio_path


def update_slideshow_task_state(job_id, output_key, status="SLIDESHOW_CREATED"):
    """`job_id` を使って DynamoDB のジョブレコードを更新する。"""
    table = globals().get("dynamodb_table")
    if table is None:
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
        except Exception as e:
            logger.error(f"Failed to update DynamoDB: {e}")
            return

    try:
        table.update_item(
            Key={"job_id": job_id},
            UpdateExpression="SET slideshow_output_key = :k, slideshow_status = :ss, #st = :s",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":k": output_key,
                ":ss": status,
                ":s": status,
                ":status": status,
                ":output_key": output_key,
            },
        )
        logger.info(f"DynamoDB updated for job_id={job_id}")
    except Exception as e:
        logger.error(f"Failed to update DynamoDB: {e}")


def update_job_in_dynamodb(job_id, output_key):
    """Backward-compatible wrapper for slideshow state updates."""
    update_slideshow_task_state(job_id, output_key)


def enqueue_format_video_job(job_id: str, bucket: str, key: str):
    """Format Video Lambda へのジョブを SQS に送信する"""
    if not job_id:
        logger.info("No job_id provided; skipping format-video enqueue")
        return

    if not QUEUE_URL_FORMAT_VIDEO:
        logger.warning(
            "QUEUE_URL_FORMAT_VIDEO not configured; skipping format-video enqueue"
        )
        return

    sqs = get_sqs_client()
    message = {"job_id": job_id, "bucket": bucket, "key": key}
    logger.info(
        "Sending format-video job to SQS",
        extra={
            "queue_url": QUEUE_URL_FORMAT_VIDEO,
            "job_id": job_id,
            "bucket": bucket,
            "key": key,
        },
    )
    sqs.send_message(QueueUrl=QUEUE_URL_FORMAT_VIDEO, MessageBody=json.dumps(message))
    logger.info("Format-video job enqueued successfully", extra={"job_id": job_id})


def lambda_handler(event, context):
    """
    S3にある画像からスライドショーを作成する

    event: SQSからのメッセージで、以下の構造:
        {
            "Records": [
                {
                    "body": '{"job_id": "...", "audio_key": "audio.mp3"}'
                }
            ]
        }
    """
    try:
        bucket = os.environ.get("BUCKET_NAME")
        if not bucket:
            raise Exception("環境変数 BUCKET_NAME が設定されていません。")

        # SQSからjob_idと音声ファイルキーを抽出
        body = json.loads(event["Records"][0]["body"])
        job_id = body.get("job_id")
        audio_key = body.get("audio_key", "audio.mp3")

        s3 = get_s3_client()

        # バケット内の全ての画像ファイルを列挙
        image_keys = list_image_keys(bucket, s3)

        if not image_keys:
            raise Exception("No image files found in the bucket")

        logger.info(f"Found {len(image_keys)} images in s3://{bucket}/")

        # 各画像をS3からダウンロードして回転処理
        processed_image_paths = []
        for i, key in enumerate(sorted(image_keys)):
            file_name = os.path.basename(key)
            local_path = f"/tmp/{i}_{file_name}"
            logger.info(f"Downloading image: {key}")
            s3.download_file(bucket, key, local_path)

            # 画像を回転
            rotated_path = rotate_image(local_path)
            processed_image_paths.append(rotated_path)

        # ffmpeg concat用ファイルを生成
        create_concat_file(processed_image_paths)

        # 画像を動画に変換
        images_to_video()

        # 音声ファイルをダウンロード
        audio_path = download_audio_from_s3(bucket, audio_key, s3)

        # 動画に音声を追加
        add_audio_to_video(audio_path)

        # S3にアップロード
        output_key = build_output_key(job_id)
        logger.info(f"Uploading slideshow to S3: s3://{bucket}/{output_key}")
        s3.upload_file(FINAL_VIDEO, bucket, output_key)

        # DynamoDB を更新
        update_slideshow_task_state(job_id, output_key)

        # フォーマット処理キューにジョブを送信
        enqueue_format_video_job(job_id, bucket, output_key)

        # クリーンアップ
        for file_path in processed_image_paths:
            if os.path.exists(file_path):
                os.remove(file_path)

        for file_path in [FFMPEG_LIST_FILE, OUTPUT_VIDEO, FINAL_VIDEO, audio_path]:
            if os.path.exists(file_path):
                os.remove(file_path)

        logger.info("Cleanup completed")

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "status": "success",
                    "job_id": job_id,
                    "output_key": output_key,
                }
            ),
        }

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"status": "error", "message": str(e)}),
        }
