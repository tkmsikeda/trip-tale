import logging

import subprocess
import json

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


with open("ffmpeg_command.json", "r") as f:
    FFMPEG_COMMAND = json.load(f)


def get_fps(video_path):

    ffmpeg_command_template = FFMPEG_COMMAND.get("get_fps")
    ffmpeg_command_formated = ffmpeg_command_template.format(
        file_path=video_path,
    )

    logger.debug(f"ffmpeg command: {ffmpeg_command_formated}")

    result = subprocess.run(
        ffmpeg_command_formated,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
        shell=True,
    )

    # 出力された "60/1" のような文字列を取得
    fps_str = result.stdout.strip()

    # 分数を計算して float に変換
    numerator, denominator = map(int, fps_str.split("/"))
    fps = numerator / denominator

    return fps
