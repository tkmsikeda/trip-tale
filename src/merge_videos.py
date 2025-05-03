import fps_getter
import make_video_base


class MergeVideos(make_video_base.MakeVideoBase):
    def __init__(self, directory: str, file_extension: str):
        super().__init__(directory, file_extension)

    # ffmpegコマンドを実行するために必要なtxtファイルを作成する
    def write_filepath_to_txtfile_for_video(self, file_names: list[str]):
        with open("video_files.txt", "w", encoding="utf-8") as file:
            for file_name in file_names:
                file.write(f"file '{file_name}'\n")

    def format_all_video(self) -> list[str]:
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

        # TODO 変数名をわかりやすくしたい
        for i, file_path in enumerate(self.file_paths):
            output_name = "formatted_" + str(i) + ".MOV"

            if fps_getter.should_change_fps(file_path):
                ffmpeg_command_template = self.FFMPEG_COMMAND["change_fps"]
            else:
                ffmpeg_command_template = self.FFMPEG_COMMAND["format"]

            ffmpeg_command_formated = ffmpeg_command_template.format(
                file_path=file_path,
                output_name=output_name,
            )
            self.run_shell_command(ffmpeg_command_formated)
            formatted_video_file_names.append(output_name)

        # TODO クラスの属性self.file_pathsを書き換えてもいいかもしれない。
        # WARNING: ただし、for文では操作しない。バグになりそう
        return formatted_video_file_names

    # TODO リファクタリング：コマンド中のファイル名を変数化したい
    # TODO: ファイルのパスをクラスの属性に含めているので、関数で受け渡し不要
    def main(self):

        # 動画の最後に写真スライドショー動画を追加すべく、対象に追記
        self.file_paths.append("./image_audio_video.MOV")

        # 動画のフォーマットを統一する
        formatted_video_file_names = self.format_all_video()

        # TODO 以下の処理は関数にまとめて、内部的に関数を呼ぶようにしたほうが可読性が高いかもしれない
        # 結合対象の動画ファイルをtxtファイルに記載
        self.write_filepath_to_txtfile_for_video(formatted_video_file_names)
        # 動画ファイルを１個の動画に結合
        self.run_shell_command(self.FFMPEG_COMMAND["merge_all_video"])
