import logging
import os

import piexif
from PIL import Image, ExifTags



logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

def _get_orientation(image_path: str) -> int:
    """
    画像の回転情報を取得する関数
    :param image_path: 画像のパス
    :return: 回転情報
    """
    with Image.open(image_path) as img:
        exif = img._getexif()
        
    default_orientation = 1
    if exif is None:
        return default_orientation
    
    # 生のexifデータのままだと、ID番号: 値の形式。
    # 回転情報がID何番かわかりずらい。※274番が回転情報
    tagname_value_map = {}
    for tag_id, value in exif.items():
        tag_name = ExifTags.TAGS.get(tag_id, tag_id)  
        tagname_value_map[tag_name] = value

    logger.debug(f"exif data of {image_path} : {tagname_value_map}")
    logger.info(f"orientation of {image_path}: {tagname_value_map.get("Orientation", default_orientation)}")

    return tagname_value_map.get("Orientation", default_orientation)

# 回転情報があると、ffmpegで動画化する際に、邪魔になる
# そのため、写真を回転させたのち、回転情報を除去する
# 出力：回転させた場合、対象ファイルのパスを書き換えたいので、その判定用
def rotate_image(image_path: str) -> tuple[bool, str]:

    is_rotated = False
    orientation = _get_orientation(image_path)
    if orientation == 1:
        logger.info("no rotate")
        return is_rotated, image_path

    with Image.open(image_path) as img:
        
        if orientation == 3:
            img_rotated = img.rotate(180, expand=True)
            logger.info("rotate 180")
            is_rotated = True
        elif orientation == 6:  # 90度回転
            img_rotated = img.rotate(270, expand=True)
            logger.info("rotate 90")
            is_rotated = True
        elif orientation == 8:  # -90度回転
            img_rotated = img.rotate(90, expand=True)
            logger.info("rotate -90")
            is_rotated = True

        # 例: image.jpg → image_rotated.jpg
        base, ext = os.path.splitext(image_path)
        tmp = f"{base}_rotated{ext}"
        filename = os.path.basename(tmp)


        exif = img._getexif()
        exif[274] = 1
        exif_dict = {"0th": {piexif.ImageIFD.Orientation: 1}}
        exif_bytes = piexif.dump(exif_dict)
        
        img_rotated.save(filename, exif=exif_bytes)
        logger.info(f"save rotated image: {filename}")
        return is_rotated, filename


if __name__ == "__main__":
    rotate_image("IMG_20250227_081855.JPG")