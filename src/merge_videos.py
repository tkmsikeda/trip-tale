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


# ffmpegコマンドを実行するために必要なtxtファイルを作成する
def write_filepath_to_txtfile_for_video(file_names: list[str]):
    with open("video_files.txt", "w", encoding="utf-8") as file:
        for file_name in file_names:
            file.write(f"file '{file_name}'\n")


# shellのコマンドでffmpegを実行する方式
# ffmpegライブラリが結局↑を実施していて、使い方も理想形ではないので、自分で書く。
def run_shell_command(shell_command: str):
    logger.debug(f"shell実行: {shell_command}")
    subprocess.run(shell_command, shell=True)


def format_all_video(file_names: list[str]) -> list[str]:
    """動画のフォーマットを統一する

    動画の種類によって、処理が変わる。ただしコマンドは同一のもの。
    横取り動画の場合: ffmpegによりコーデックされるのみ
    縦どり動画の場合: ffmpegによりコーデックされる事に加え、90度回転後に、
    解像度を1920x1080に変換し、余った横枠に黒枠を追加する

    ffmpegコマンドの詳細
    -loglevel quiet : ffmpegの標準出力を抑制
    -vf "scale=1920:1080: 解像度を1920x1080に変換
    :force_original_aspect_ratio=decrease: アスペクト比を維持
    pad=1920:1080:(ow-iw)/2:(oh-ih)/2": 余った横枠へ黒枠を追加する
    transposeオプションを指定しなくても、自動的に解釈して、回転してくれる。

    Args:
        file_names(list[str]): 動画ファイルのリスト

    Returns:
        formatted_video_file_names(list[str]): フォーマット後の動画ファイル名のリスト
    """
    formatted_video_file_names = []

    for i, file_name in enumerate(file_names):
        output_name = "formatted_" + str(i) + ".MOV"
        ffmpeg_command_template = FFMPEG_COMMAND["format"]
        ffmpeg_command_formated = ffmpeg_command_template.format(
            file_name=file_name,
            output_name=output_name,
        )
        run_shell_command(ffmpeg_command_formated)
        formatted_video_file_names.append(output_name)

    return formatted_video_file_names


# TODO リファクタリング：コマンド中のファイル名を変数化したい
def main():
    """メイン関数"""
    # 対象のディレクトリを指定（例: 現在のディレクトリ）
    directory = "/mnt/nas/20500101_自動化テスト用"

    # 動画ファイル一覧を取得
    video_file_names = get_file_names(directory, "MOV")

    # 動画の最後に写真スライドショー動画を追加すべく、対象に追記
    video_file_names.append("./image_audio_video.MOV")

    # 動画のフォーマットを統一する
    formatted_video_file_names = format_all_video(video_file_names)

    # TODO 以下の処理は関数にまとめて、内部的に関数を呼ぶようにしたほうが可読性が高いかもしれない
    # 結合対象の動画ファイルをtxtファイルに記載
    write_filepath_to_txtfile_for_video(formatted_video_file_names)
    # 動画ファイルを１個の動画に結合
    run_shell_command(FFMPEG_COMMAND["merge_all_video"])


if __name__ == "__main__":
    main()
