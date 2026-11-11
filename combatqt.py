"""전투 모습 미리보기 (Tk 의 pet_preview 와 같다): 게임 배경 위에 그림을 발밑 기준으로 세워 보여 준다.

게임 파일이 없으면 짙은 초록 배경에 그린다. 그림이 없으면 임시 외형 자리에 빈 그림을 쓴다.
"""
from PIL import Image, ImageDraw

import gamescene as GS
import pets as PT
import preview_qt as PQ


def combat_pixmap(assets, image, scale, flip, lift, label, width=300, height=320):
    """(QPixmap). assets 는 게임 파일 묶음 또는 None. image 는 그림 파일 경로 또는 빈 값(임시 그림)."""
    cw, ch = width, height
    k = 0.5                                      # 게임 1px = 미리보기 0.5px
    bg = None
    if assets is not None:
        try:
            full = GS.background(assets)
            fx, fy = GS.PLAYER
            box = (int(fx - cw / k / 2), int(fy - (ch - 30) / k), int(fx + cw / k / 2), int(fy + 30 / k))
            bg = full.crop(box).resize((cw, ch), Image.LANCZOS)
        except Exception:  # noqa: BLE001 - 배경을 못 읽어도 미리보기는 그린다
            bg = None
    if bg is None:
        bg = Image.new("RGBA", (cw, ch), (28, 42, 34, 255))
    draw = ImageDraw.Draw(bg)
    feet = (cw // 2, ch - 30)
    draw.ellipse((feet[0] - 60, feet[1] - 8, feet[0] + 60, feet[1] + 8), fill=(0, 0, 0, 90))
    try:
        im = PT.process_image(image, scale, flip, lift) if image else PT.placeholder()
    except (OSError, ValueError):
        im = PT.placeholder()
    im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
    bg.alpha_composite(im, (int(feet[0] - im.width / 2), int(feet[1] - im.height)))
    draw.text((6, 6), f"{label}  ({im.width * 2}×{im.height * 2}px)", fill=(230, 230, 230, 255))
    return PQ._qpixmap(bg)
