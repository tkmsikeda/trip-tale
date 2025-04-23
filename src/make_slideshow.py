import image_rotater
import make_video_base


class Makesladeshow(make_video_base.MakeVideoBase):
    def __init__(self, directory: str, file_extension: str):
        super().__init__(directory, file_extension)

    def write_filepath_to_txtfile_for_image(self):
        with open("image_files.txt", "w", encoding="utf-8") as file:
            for file_path in self.file_paths:
                file.write(f"file '{file_path}'\nduration 5\n")
            # ffmpegの仕様で最後のファイルを2度書かないと表示してくれないので、追記。
            file.write(f"file '{self.file_paths[-1]}'")

    def rotate_images(self):
        for index, file_path in enumerate(self.file_paths):
            is_rotated, image_path = image_rotater.rotate_image(file_path)
            if is_rotated:
                # 回転させた写真は、別ファイルかつ置き場が違うため、書き換える
                self.file_paths[index] = image_path
                

    # TODO: 一時的な動画ファイルを最後に削除する

    def main(self):

        self.logger.info("画像からスライドショー作成開始")
        self.logger.info("対象画像ファイルを取得")

        # ffmpegの制限で、回転情報を揃えないと、写真が横向きに表示されるため、前処理する
        self.rotate_images()

        # TODO ファイルが0個の時の処理を書く

        # ffmpegコマンドを実行するために必要なファイルを作成する
        self.write_filepath_to_txtfile_for_image()

        # 音楽なしのスライドショー動画作成
        self.run_shell_command(self.FFMPEG_COMMAND["convert_images_to_video"])
        # スライドショーに音楽を追加した動画に変換
        self.run_shell_command(self.FFMPEG_COMMAND["add_audio_to_video"])
