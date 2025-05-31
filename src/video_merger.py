import fps_getter
import maker_base


class VideoMerger(maker_base.MakerBase):
    FFMPEG_LIST_FILE = "video_files.txt"

    def __init__(self, directory: str, file_extension: str):
        super().__init__(directory, file_extension)
        self.target_video_paths: list = []

    def _select_ffmpeg_by_fps(self, file_path: str) -> str:
        """動画のFPSに応じて、ffmpegコマンドを選択する

        Args:
            file_path(str): 動画ファイルのパス

        Returns:
            ffmpeg_command(str): 選択されたffmpegコマンド
        """
        if fps_getter.should_change_fps(file_path):
            return self.FFMPEG_COMMAND["change_fps"]
        else:
            return self.FFMPEG_COMMAND["format"]

    def _format_all_video(self):
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
        """

        for i, file_path in enumerate(self.file_paths):
            output_name = "formatted_" + str(i) + ".MOV"

            # ffmpegの制約で動画のFPSを統一しないと、最後に結合できない
            ffmpeg_command = self._select_ffmpeg_by_fps(file_path).format(
                file_path=file_path,
                output_name=output_name,
            )
            self.run_shell_command(ffmpeg_command)

            self.target_video_paths.append(output_name)

    def _write_ffmpeg_list(self):
        with open(self.FFMPEG_LIST_FILE, "w", encoding="utf-8") as file:
            for file_path in self.target_video_paths:
                file.write(f"file '{file_path}'\n")

    def _merge_videos_with_ffmpeg(self):
        self._write_ffmpeg_list()
        self.run_shell_command(self.FFMPEG_COMMAND["merge_all_video"])

    # TODO リファクタリング：コマンド中のファイル名を変数化したい
    def merge_videos(self):

        if not self.file_paths:
            self.logger.warning(
                "対象の動画ファイルがありません。動画を作成できません。"
            )
            return

        # 動画の最後に、スライドショー動画を追加するために、対象に追記
        self.file_paths.append("./image_audio_video.MOV")

        # ffmpegの制約で、フォーマットを統一する前処理を実施
        self._format_all_video()

        self._merge_videos_with_ffmpeg()
