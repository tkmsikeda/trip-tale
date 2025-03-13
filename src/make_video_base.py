import glob
import logging
import subprocess


class MakeVideoBase:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.DEBUG)
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def get_file_names(self, directory: str, file_extension: str) -> list:
        file_names = glob.glob(directory + f"/*.{file_extension}")
        file_names.sort()
        self.logger.info(
            f"{len(file_names)} 個の{file_extension}ファイルが見つかりました"
        )
        for file_name in file_names:
            self.logger.debug(file_name)
        return file_names

    def run_shell_command(self, shell_command: str):
        self.logger.debug(f"shell実行: {shell_command}")
        subprocess.run(shell_command, shell=True)
