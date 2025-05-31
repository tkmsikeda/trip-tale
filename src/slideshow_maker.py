import image_rotater
import make_video_base


class SlideshowMaker(make_video_base.MakeVideoBase):
    DURATION_PER_IMAGE_SECONDS = 5
    FFMPEG_LIST_FILE = "image_files.txt"

    def __init__(self, directory: str, file_extension: str):
        super().__init__(directory, file_extension)

    def _rotate_images(self):
        for index, file_path in enumerate(self.file_paths):
            is_rotated, image_path = image_rotater.rotate_image(file_path)
            if is_rotated:
                # 回転させた写真は、別ファイルかつ置き場が違うため、書き換える
                self.file_paths[index] = image_path

    def _write_ffmpeg_list(self):
        with open(self.FFMPEG_LIST_FILE, "w", encoding="utf-8") as file:
            for file_path in self.file_paths:
                file.write(f"file '{file_path}'\n")
                file.write(f"duration {self.DURATION_PER_IMAGE_SECONDS}\n")

            # ffmpegの仕様で最後のファイルを2度書かないと表示してくれないので、追記。
            file.write(f"file '{self.file_paths[-1]}'")

    def _images_to_video(self):
        self.run_shell_command(self.FFMPEG_COMMAND["convert_images_to_video"])

    def _add_music(self):
        self.run_shell_command(self.FFMPEG_COMMAND["add_audio_to_video"])

    # TODO: 一時的な動画ファイルを最後に削除する

    def create_slideshow(self):

        self.logger.info("画像からスライドショー作成開始")

        if not self.file_paths:
            self.logger.warning(
                "対象の画像ファイルがありません。スライドショーを作成できません。"
            )
            return

        # ffmpegの制限で、回転情報を揃えないと、写真が横向きに表示されるため、前処理する
        self._rotate_images()

        self._write_ffmpeg_list()
        self._images_to_video()
        self._add_music()
