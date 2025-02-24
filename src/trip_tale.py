import glob
import logging
import subprocess


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


def get_file_names(directory: str) -> list:
    """指定したディレクトリ内のファイルとフォルダをリストアップする関数"""

    movie_file_names = glob.glob(directory + "/*.MOV")

    # 撮影順でソート
    movie_file_names.sort()
    logger.info(f"{len(movie_file_names)} 個の動画ファイルが見つかりました")

    return movie_file_names


# ffmpegコマンドを実行するために必要なtxtファイルを作成する
def write_filepath_to_txtfile(file_names: list[str]):
    logger.debug("start write_filepath_to_txtfile")
    with open("files.txt", "w", encoding="utf-8") as file:
        for file_name in file_names:
            file.write(f"file '{file_name}'\n")
            logger.debug(f"files.txtへの書き込み内容: file '{file_name}'")


# moviepyだと問題２個ありなので、ffmpegを利用した。
# 問題1. 動画を結合するとbitrateが下がる。動画の画質ダウンになりそう
# 問題2. スマートフォンで縦撮影の動画だと、解像度とアスペクト比が変わる。
# shellのコマンドでffmpegを実行する方式
# ffmpegライブラリが結局↑を実施していて、使い方も理想形ではないので、自分で書く。
def merge_movies_ffmpeg():
    output_file_name = "final_video.MOV"
    shell_command = f"ffmpeg -f concat -safe 0 -i files.txt -c copy {output_file_name}"

    logger.debug(f"shell実行: {shell_command}")
    subprocess.run(shell_command, shell=True)


def main():
    """メイン関数"""
    # 対象のディレクトリを指定（例: 現在のディレクトリ）
    directory = "/mnt/nas/20500101_自動化テスト用"

    # ファイル一覧を取得
    file_names = get_file_names(directory)

    write_filepath_to_txtfile(file_names)

    # 動画ファイルを１個の動画に結合
    # merge_movies(file_names)
    merge_movies_ffmpeg()


if __name__ == "__main__":
    main()
