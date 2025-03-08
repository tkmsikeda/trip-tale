import glob
import json
import logging
import subprocess


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

with open("ffmpeg_command.json", "r") as f:
    FFMPEG_COMMAND = json.load(f)


def get_file_names(directory: str, file_extension: str) -> list:
    """指定したディレクトリ内のファイルとフォルダをリストアップする関数"""

    file_names = glob.glob(directory + f"/*.{file_extension}")

    # 撮影順でソート
    file_names.sort()
    logger.info(f"{len(file_names)} 個の{file_extension}ファイルが見つかりました")
    for file_name in file_names:
        logger.debug(file_name)

    return file_names


# TODO  write_filepath_to_txtfile関数と共通部分が多いので1個にできないか？
# 写真からスライドショー動画に変換する対象の写真ファイルを追記
def write_filepath_to_txtfile_for_image(file_names: list[str]):
    with open("image_files.txt", "w", encoding="utf-8") as file:
        for file_name in file_names:
            file.write(f"file '{file_name}'\nduration 5\n")
        # ffmpegの仕様で最後のファイルを2度書かないと表示してくれないので、追記。
        file.write(f"file '{file_names[-1]}'")


# shellのコマンドでffmpegを実行する方式
# ffmpegライブラリが結局↑を実施していて、使い方も理想形ではないので、自分で書く。
def run_shell_command(shell_command: str):
    logger.debug(f"shell実行: {shell_command}")
    subprocess.run(shell_command, shell=True)


# TODO リファクタリング：コマンド中のファイル名を変数化したい
def main():
    """メイン関数"""
    # 対象のディレクトリを指定（例: 現在のディレクトリ）
    directory = "/mnt/nas/20500101_自動化テスト用"

    logger.info("画像からスライドショー作成開始")
    logger.info("対象画像ファイルを取得")
    image_file_names = get_file_names(directory, "JPG")
    write_filepath_to_txtfile_for_image(image_file_names)
    # 音楽なしのスライドショー動画作成
    run_shell_command(FFMPEG_COMMAND["convert_images_to_video"])
    # スライドショーに音楽を追加した動画に変換
    run_shell_command(FFMPEG_COMMAND["add_audio_to_video"])


if __name__ == "__main__":
    main()
