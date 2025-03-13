import json

import make_video_base


with open("ffmpeg_command.json", "r") as f:
    FFMPEG_COMMAND = json.load(f)


class Makesladeshow(make_video_base.MakeVideoBase):
    def __init__(self):
        super().__init__()

    def write_filepath_to_txtfile_for_image(self, file_names: list[str]):
        with open("image_files.txt", "w", encoding="utf-8") as file:
            for file_name in file_names:
                file.write(f"file '{file_name}'\nduration 5\n")
            # ffmpegの仕様で最後のファイルを2度書かないと表示してくれないので、追記。
            file.write(f"file '{file_names[-1]}'")

    def main(self):
        """メイン関数"""
        # 対象のディレクトリを指定
        directory = "/mnt/nas/20500101_自動化テスト用"

        self.logger.info("画像からスライドショー作成開始")
        self.logger.info("対象画像ファイルを取得")

        image_file_names = self.get_file_names(directory, "JPG")

        # TODO ファイルが0個の時の処理を書く

        self.write_filepath_to_txtfile_for_image(image_file_names)
        # 音楽なしのスライドショー動画作成
        self.run_shell_command(FFMPEG_COMMAND["convert_images_to_video"])
        # スライドショーに音楽を追加した動画に変換
        self.run_shell_command(FFMPEG_COMMAND["add_audio_to_video"])
