import logging

import slideshow_maker
import video_merger

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


# TODO リファクタリング：コマンド中のファイル名を変数化したい
def main():
    """メイン関数"""
    directory = "xxx"

    try:
        logger.info("画像からスライドショー作成開始")
        slideshow_maker.SlideshowMaker(directory, "JPG").create_slideshow()
        logger.info("画像からスライドショー作成完了")

        logger.info("全ての動画を結合開始")
        video_merger.VideoMerger(directory, "MOV").merge_videos()
        logger.info("全ての動画を結合完了")

    except Exception as e:
        logger.error(f"動画作成失敗: {e}")


if __name__ == "__main__":
    main()
