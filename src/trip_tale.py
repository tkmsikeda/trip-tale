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


# ffmpegコマンドを実行するために必要なtxtファイルを作成する
def write_filepath_to_txtfile_for_movie(file_names: list[str]):
    with open("movie_files.txt", "w", encoding="utf-8") as file:
        for file_name in file_names:
            file.write(f"file '{file_name}'\n")


def update_taget_list(
    movie_file_names: list[str], rotated_video_indexs: list[int]
) -> list:
    updated_target_list = movie_file_names.copy()
    for rotated_video_index in rotated_video_indexs:
        updated_target_list[rotated_video_index] = (
            "rotated_" + str(rotated_video_index) + ".MOV"
        )
    return updated_target_list


# 縦どり動画を変換する関数
# 変換1: 縦どりの動画を90度回転させる。
# 変換2: 解像度を1920x1080に変換する。
# 変換3: スケーリングにより余った横枠を黒枠を追加する。paddingするとも呼ぶ模様。
def scale_and_pad_video(file_names: list[str], target_indexs) -> None:

    ffmpeg_command_template = FFMPEG_COMMAND["rotate"]
    # -loglevel quiet : ffmpegの標準出力を抑制
    # -vf "scale=1920:1080: 解像度を1920x1080に変換
    # :force_original_aspect_ratio=decrease: アスペクト比を維持
    # pad=1920:1080:(ow-iw)/2:(oh-ih)/2": 余った横枠へ黒枠を追加する
    # transposeオプションを指定しなくても、自動的に解釈して、回転してくれる。

    for target_index in target_indexs:
        ffmpeg_command_formated = ffmpeg_command_template.format(
            file_name=file_names[target_index],
            output_name="rotated_" + str(target_index) + ".MOV",
        )
        run_shell_command(ffmpeg_command_formated)

    return


def get_movie_metadata(file_name: str) -> dict:
    get_metadata_shell_command = (
        "ffprobe -loglevel quiet -show_streams -print_format json"
        + f" {file_name} > movie_metadata.json"
    )
    # -loglevel quiet: ffmpegの標準出力を抑制
    # -show_streams: メタデータを表示する
    # -print_format json: json形式で出力する
    # > movie_metadata.json: 出力結果をmovie_metadata.jsonに保存する
    run_shell_command(get_metadata_shell_command)
    with open("movie_metadata.json", "r") as movie_metadata_json:
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
        # side_data_listがない≒横で撮影した動画なので次のループへ
        if side_data_list == 0:
            continue
        rotation = side_data_list[0].get("rotation")
        logger.info(f"{file_name} rotation: {rotation}")
        if rotation != 0:
            rotated_video_indexs.append(i)

    return rotated_video_indexs


# moviepyだと問題２個ありなので、ffmpegを利用した。
# 問題1. 動画を結合するとbitrateが下がる。動画の画質ダウンになりそう。
#        ->ffmpegコマンドだと下がらない。
# 問題2. スマートフォンで縦撮影の動画だと、解像度とアスペクト比が変わる。
# shellのコマンドでffmpegを実行する方式
# ffmpegライブラリが結局↑を実施していて、使い方も理想形ではないので、自分で書く。
def run_shell_command(shell_command: str):
    logger.debug(f"shell実行: {shell_command}")
    subprocess.run(shell_command, shell=True)


def format_all_movie(file_names: list[str]) -> list[str]:
    """動画のフォーマットを統一する

    動画の種類によって、処理が変わる。ただしコマンドは同一のもの。
    横取り動画の場合: ffmpegによりコーデックされるのみ
    縦どり動画の場合: ffmpegによりコーデックされる事に加え、解像度を1920x1080に変換し
    余った横枠に黒枠を追加する

    Args:
        file_names(list[str]): 動画ファイルのリスト

    Returns:
        formatted_movie_file_names(list[str]): フォーマット後の動画ファイル名のリスト
    """
    formatted_movie_file_names = []

    for i, file_name in enumerate(file_names):
        output_name = "formatted_" + str(i) + ".MOV"
        ffmpeg_command_template = FFMPEG_COMMAND["format"]
        ffmpeg_command_formated = ffmpeg_command_template.format(
            file_name=file_name,
            output_name=output_name,
        )
        run_shell_command(ffmpeg_command_formated)
        formatted_movie_file_names.append(output_name)

    return formatted_movie_file_names


# TODO リファクタリング：コマンド中のファイル名を変数化したい
def main():
    """メイン関数"""
    # 対象のディレクトリを指定（例: 現在のディレクトリ）
    directory = "/mnt/nas/20500101_自動化テスト用"

    # TODO 以下のコマンドは、ffmpeg_command.jsonに外だしして読み込む
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
    # run_shell_command(shell_command_for_image_file)
    # # スライドショーに音楽を追加した動画に変換
    # run_shell_command(shell_command_for_add_auido)

    # 動画ファイル一覧を取得
    movie_file_names = get_file_names(directory, "MOV")
    # 動画のフォーマットを統一する
    formatted_movie_file_names = format_all_movie(movie_file_names)

    # # 縦撮影の動画を見つける
    # rotated_video_indexs = extract_rotated_video(movie_file_names)
    # # 縦撮影の動画を変換する。原本動画は変えない。一時ファイルをローカルに配置する。
    # scale_and_pad_video(movie_file_names, rotated_video_indexs)
    # # movie_file_namesへ縦どり動画のパスで更新
    # movie_file_names = update_taget_list(movie_file_names, rotated_video_indexs)
    # print(movie_file_names)

    # # 動画の最後に写真スライドショー動画を追加すべく、対象に追記
    # movie_file_names.append("./image_audio_video.mp4")

    # TODO 以下の処理は関数にまとめて、内部的に関数を呼ぶようにしたほうが可読性が高いかもしれない
    # 結合対象の動画ファイルをtxtファイルに記載
    write_filepath_to_txtfile_for_movie(formatted_movie_file_names)
    # 動画ファイルを１個の動画に結合
    run_shell_command(shell_command_for_movie_file)


if __name__ == "__main__":
    main()
