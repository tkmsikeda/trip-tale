import image_rotater
import maker_base


class SlideshowMaker(maker_base.MakerBase):
    DURATION_PER_IMAGE_SECONDS = 5
    FFMPEG_LIST_FILE = "image_files.txt"

    def __init__(self, directory: str, file_extension: str):
        super().__init__(directory, file_extension)
        self.target_image_paths: list = []

    def _rotate_images(self):
        for file_path in self.file_paths:
            image_path = image_rotater.rotate_image(file_path)

            # 回転させてない写真：元々の置き場
            # 回転させた写真：ローカル
            self.target_image_paths.append(image_path)

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
