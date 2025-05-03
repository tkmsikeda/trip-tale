import glob
import json
import logging
import subprocess


class MakeVideoBase:
    def __init__(self, directory: str, file_extension: str):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.file_paths = self._get_file_paths(directory, file_extension)
        self.FFMPEG_COMMAND = self._get_ffmpeg_commands()

    def _get_file_paths(self, directory: str, file_extension: str) -> list:
        file_paths = glob.glob(directory + f"/*.{file_extension}")
        file_paths.sort()
        self.logger.info(
            f"{len(file_paths)} 個の{file_extension}ファイルが見つかりました"
        )
        for file_path in file_paths:
            self.logger.debug(file_path)
        return file_paths
    
    def _get_ffmpeg_commands(self) -> dict[str, str]:
        with open("ffmpeg_command.json", "r") as f:
            ffmpeg_command = json.load(f)
        return ffmpeg_command


    def run_shell_command(self, shell_command: str):
        self.logger.debug(f"shell実行: {shell_command}")
        subprocess.run(shell_command, shell=True)
