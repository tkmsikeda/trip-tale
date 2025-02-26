import glob
import logging
import subprocess


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
def write_filepath_to_txtfile_for_image(file_names: list[str]):
    with open("image_files.txt", "w", encoding="utf-8") as file:
        for file_name in file_names:
            file.write(f"file '{file_name}'\nduration 5\n")
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


# moviepyだと問題２個ありなので、ffmpegを利用した。
# 問題1. 動画を結合するとbitrateが下がる。動画の画質ダウンになりそう。
#        ->ffmpegコマンドだと下がらない。
# 問題2. スマートフォンで縦撮影の動画だと、解像度とアスペクト比が変わる。
# shellのコマンドでffmpegを実行する方式
# ffmpegライブラリが結局↑を実施していて、使い方も理想形ではないので、自分で書く。
def merge_movies_ffmpeg(shell_command: str):
    # shell_command = "ffmpeg -f concat -safe 0 -i files.txt -c copy final_video.MOV"
    logger.debug(f"shell実行: {shell_command}")
    subprocess.run(shell_command, shell=True)


def main():
    """メイン関数"""
    # 対象のディレクトリを指定（例: 現在のディレクトリ）
    directory = "/mnt/nas/20500101_自動化テスト用"
    shell_command_for_movie_file = (
        "ffmpeg -f concat -safe 0 -i movie_files.txt -c copy final_video.MOV"
    )
    shell_command_for_image_file = (
        "ffmpeg -f concat -safe 0 -i image_files.txt"
        + " -vsync vfr -vcodec libx264"
        + ' -vf "scale=1920:1080:force_original_aspect_ratio=decrease,'
        + 'pad=1920:1080:(ow-iw)/2:(oh-ih)/2"'
        + " -pix_fmt yuv420p output.mp4"
    )
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
    # -shortest: により動画の長さでカットされる。

    # 動画ファイル一覧を取得
    # movie_file_names = get_file_names(directory, "MOV")
    # write_filepath_to_txtfile_for_movie(movie_file_names)
    # # 動画ファイルを１個の動画に結合
    # merge_movies_ffmpeg(shell_command_for_movie_file)

    logger.info("画像からスライドショー作成開始")
    logger.info("対象画像ファイルを取得")
    image_file_names = get_file_names(directory, "JPG")
    write_filepath_to_txtfile_for_image(image_file_names)
    merge_movies_ffmpeg(shell_command_for_image_file)
    merge_movies_ffmpeg(shell_command_for_add_auido)


if __name__ == "__main__":
    main()
