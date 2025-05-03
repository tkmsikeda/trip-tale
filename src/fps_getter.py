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

def should_change_fps(video_path: str) -> bool:
    """ fpsの変更が必要かチェックする関数
    ffmpegでは、fpsが30, 60以外の動画を結合するとスロー再生になる。
    スマホ撮影だとfpsが動的で、30, 60に加えて59.94等ということもある。
    例：fps: 30 -> return: false, fps: 59.94 -> return: true
    """
    fps_skip_encode = (30.0, 60.0)
    fps = _get_fps(video_path)
    logger.info(f"{video_path} fps: {fps}")

    return fps not in fps_skip_encode

    

def _get_fps(video_path):
    

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
    numerator, denominator = map(int, fps_str.split('/'))
    fps = numerator / denominator
    
    return fps


if __name__ == "__main__":
    # 使用例
    for i in range(81, 112):
        video_file = f"formatted_{i}.MOV"
        if should_change_fps(video_file):
            print("エンコードが必要です。")