import glob

from moviepy import VideoFileClip, concatenate_videoclips


def get_file_names(directory: str) -> list:
    """指定したディレクトリ内のファイルとフォルダをリストアップする関数"""
    movie_file_names = glob.glob(directory + "/*.MOV")

    # 撮影順でソート
    movie_file_names.sort()

    return movie_file_names


def merge_movies(file_names: list[str]):
    """
    目的：複数の動画ファイルを１個の動画に結合すること
    入力：ファイル名
    出力：なし
    処理：moviepyモジュールのVideoFileClipクラスを利用する
    TODO(ikeda) 動画の縦横の比率が結合後に代わってしまっているので解消する
    """
    clips = []
    for file_name in file_names:
        clip = VideoFileClip(file_name)
        clips.append(clip)

    # 動画を結合
    final_clip = concatenate_videoclips(clips)
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
