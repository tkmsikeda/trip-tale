import glob
import json
import logging
import subprocess

import cv2


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


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


# ffmpegコマンドを実行するために必要なtxtファイルを作成する
def write_filepath_to_txtfile_for_movie(file_names: list[str]):
    with open("movie_files.txt", "w", encoding="utf-8") as file:
        for file_name in file_names:
            file.write(f"file '{file_name}'\n")


# 縦どり動画を変換する関数
# 変換1: 解像度（1080x1920）をフルHD（1920x1080）にスケーリングする
# 変換2: スケーリングにより余った横枠を黒枠を追加する。paddingするとも呼ぶ模様。
# TODO まず期待する動画へ編集できるffmpegコマンドを探る.いったん候補としては以下。テスト用動画撮影して、コマンド試す。
# ffmpeg -i input_video.mp4 -vf "scale=1920:1080, pad=1920:1080:(ow-iw)/2:(oh-ih)/2" -c:a copy output_video.mp4
# TODO その後python化
# TODO 縦どり動画かどうかを判定する関数を作成する
def scale_and_pad_video():
    return


def get_movie_metadata(file_name: str) -> dict:
    get_metadata_shell_command = (
        "ffprobe -loglevel quiet -show_streams -print_format json"
        + f" {file_name} > movie_metadata.json"
    )
    merge_movies_ffmpeg(get_metadata_shell_command)
    movie_metadata_json = open("movie_metadata.json", "r")
    movie_metadata = json.load(movie_metadata_json)

    return movie_metadata


def extract_rotated_video(file_names: list[str]) -> list[int]:
    """縦で撮影された動画を見つける

    目的: ffmpegだと、横撮影動画と縦撮影動画を結合すると、
    縦撮影動画が横向きになってしまう。
    縦動画を見つけ出し、後続処理で、編集する
    処理: 縦撮影の動画はメタデータのrotetoが0以外なので、rotateで判定する

    Args:
        file_names(list[str]): 結合対象の動画のファイルpath一覧

    Returns:
        rotated_video_indexs(list[int]): rotateが0以外の動画が存在するlistのindex
    """
    rotated_video_indexs = []

    for i, file_name in enumerate(file_names):
        movie_metadata = get_movie_metadata(file_name)
        side_data_list = movie_metadata["streams"][0].get("side_data_list", 0)
        if side_data_list == 0:
            continue
        rotation = side_data_list[0].get("rotation")
        logger.info(f"{file_name} rotation: {rotation}")
        if rotation != 0:
            rotated_video_indexs.append(i)

    return rotated_video_indexs


def extract_non_fullhd_videos(file_names: list[str]) -> list[int]:
    """1920x1080以外の解像度の動画を見つける

    目的：ffmpegにおいて、解像度の異なる複数の動画を結合できないので
    解像度が1920x1080以外の動画を見つけ出すこと

    Args:
        file_names(list[str]): 結合対象の動画のファイルpath一覧

    Returns:
        non_fullhd_video_indexs(list[int]): 1920x1080以外の動画が存在するlistのindex
    """

    FULLHD_WIDTH_PX = 1920
    FULLHD_HEIGHT_PX = 1080

    non_fullhd_video_indexs = []
    for i, file_name in enumerate(file_names):
        cap = cv2.VideoCapture(file_name)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        if width != FULLHD_WIDTH_PX or height != FULLHD_HEIGHT_PX:
            non_fullhd_video_indexs.append(i)
            logger.debug(
                f"Found Non FullHD : {file_name}"
                + f", width: {width}, height: {height}, index: {i}"
            )

    return non_fullhd_video_indexs


# moviepyだと問題２個ありなので、ffmpegを利用した。
# 問題1. 動画を結合するとbitrateが下がる。動画の画質ダウンになりそう。
#        ->ffmpegコマンドだと下がらない。
# 問題2. スマートフォンで縦撮影の動画だと、解像度とアスペクト比が変わる。
# shellのコマンドでffmpegを実行する方式
# ffmpegライブラリが結局↑を実施していて、使い方も理想形ではないので、自分で書く。
# TODO 関数名と中身が伴わなくなってきたので、適切な名前に変える
def merge_movies_ffmpeg(shell_command: str):
    # shell_command = "ffmpeg -f concat -safe 0 -i files.txt -c copy final_video.MOV"
    logger.debug(f"shell実行: {shell_command}")
    subprocess.run(shell_command, shell=True)


# TODO リファクタリング：関数名を適切にしたい
# TODO リファクタリング：ファイル名を変数化したい
# TODO リファクタリング: コマンドをJSONファイルに外だしして読み込む
def main():
    """メイン関数"""
    # 対象のディレクトリを指定（例: 現在のディレクトリ）
    directory = "/mnt/nas/20500101_自動化テスト用"
    # 複数の動画ファイルを結合して1個の動画にするshellコマンド
    shell_command_for_movie_file = (
        "ffmpeg -f concat -safe 0 -i movie_files.txt -c copy final_video.MOV"
    )
    # 複数の画像ファイルを結合してスライドショー動画にするshellコマンド
    shell_command_for_image_file = (
        "ffmpeg -f concat -safe 0 -i image_files.txt"
        + " -vsync vfr -vcodec libx264"
        + ' -vf "scale=1920:1080:force_original_aspect_ratio=decrease,'
        + 'pad=1920:1080:(ow-iw)/2:(oh-ih)/2"'
        + " -pix_fmt yuv420p output.mp4"
    )
    # 無音のスライドショー動画に音楽を追加するshellコマンド
    shell_command_for_add_auido = (
        "ffmpeg -stream_loop -1 -i audio.mp3 -i output.mp4"
        + " -c:v copy -c:a aac -shortest image_audio_video.mp4"
    )
    # -i video.mp4：入力動画（無音）
    # -i audio.mp3：入力音声ファイル
    # -c:v copy： 動画の再エンコードを避けてそのままコピー
    # -c:a aac： 音声コーデックを AAC に指定
    # image_audio_video.mp4： 出力ファイル名
    # -stream_loop -1: 音声がループされ、動画の長さに合わせられる。
    # -shortest: 音声が動画の長さでカットされる。

    # logger.info("画像からスライドショー作成開始")
    # logger.info("対象画像ファイルを取得")
    # image_file_names = get_file_names(directory, "JPG")
    # write_filepath_to_txtfile_for_image(image_file_names)
    # # 音楽なしのスライドショー動画作成
    # merge_movies_ffmpeg(shell_command_for_image_file)
    # # スライドショーに音楽を追加した動画に変換
    # merge_movies_ffmpeg(shell_command_for_add_auido)

    # 動画ファイル一覧を取得
    movie_file_names = get_file_names(directory, "MOV")

    # 縦撮影の動画を見つける
    rotated_video_indexs = extract_rotated_video(movie_file_names)

    # TODO 1920x1080へ解像度を変換する
    # TODO ファイルパスに加える

    # # 動画の最後に写真スライドショー動画を追加すべく、対象に追記
    # movie_file_names.append("./image_audio_video.mp4")
    # 結合対象の動画ファイルをtxtファイルに記載
    # write_filepath_to_txtfile_for_movie(movie_file_names)
    # # 動画ファイルを１個の動画に結合
    # merge_movies_ffmpeg(shell_command_for_movie_file)


if __name__ == "__main__":
    main()
