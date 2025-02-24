import glob
import logging

from moviepy import VideoFileClip, concatenate_videoclips


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


def merge_movies(file_names: list[str]):
    """
    目的: 複数の動画ファイルを１個の動画に結合すること
    入力: ファイル名
    出力: なし
    処理: moviepyモジュールのVideoFileClipクラスを利用する
    TODO(ikeda) 動画の縦横の比率が結合後に代わってしまっているので解消する
    TODO concatenate_videoclipsは関数なので直接インポートしない
    """
    clips = []
    for file_name in file_names:
        logger.info(f"{file_name} を読み込み中")
        clip = VideoFileClip(file_name)
        clips.append(clip)
        logger.debug(f"編集前の{file_name}ファイルのサイズ(w, h): {clip.size}")

    # 動画を結合
    final_clip = concatenate_videoclips(clips, method="chain")
    logger.debug(f"編集後のファイルのサイズ(w, h): {final_clip.size}")

    # 結果をファイルに出力
    final_clip.write_videofile("final_video.MOV", codec="libx264")

    return


def main():
    """メイン関数"""
    # 対象のディレクトリを指定（例: 現在のディレクトリ）
    directory = "/mnt/nas/20500101_自動化テスト用"

    # ファイル一覧を取得
    file_names = get_file_names(directory)

    # 動画ファイルを１個の動画に結合
    merge_movies(file_names)


if __name__ == "__main__":
    main()
