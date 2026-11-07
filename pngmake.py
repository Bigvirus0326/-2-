"""의존성 없는 간단한 PNG 생성기 (플레이스홀더 이미지용)."""
import struct
import zlib


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def hex_to_rgb(h: str):
    h = (h or "ffffff").lstrip("#")
    if len(h) != 6:
        h = "ffffff"
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def write_png(path, width, height, shape="rect", color="#888888", border="#222222", outline_only=False):
    """shape: rect(카드 그림), circle(유물/에너지), potion(물약 병 모양)."""
    fr, fg, fb = hex_to_rgb(color)
    br, bg, bb = hex_to_rgb(border)
    cx, cy = (width - 1) / 2, (height - 1) / 2
    rows = []
    bw = max(2, min(width, height) // 24)
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            a = 0
            r = g = b = 0
            if shape == "rect":
                inside = True
                edge = x < bw or y < bw or x >= width - bw or y >= height - bw
                # 대각선 줄무늬로 '임시 그림' 느낌
                stripe = ((x + y) // max(4, width // 16)) % 2 == 0
                if inside:
                    a = 255
                    if edge:
                        r, g, b = br, bg, bb
                    else:
                        k = 1.0 if stripe else 0.82
                        r, g, b = int(fr * k), int(fg * k), int(fb * k)
            elif shape in ("circle", "potion"):
                if shape == "circle":
                    rad = min(width, height) * 0.42
                    d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                    inside = d <= rad
                    edge = rad - bw <= d <= rad
                else:
                    # 병: 아래 원 + 위 목
                    rad = min(width, height) * 0.30
                    by = cy + height * 0.12
                    d = ((x - cx) ** 2 + (y - by) ** 2) ** 0.5
                    neck = abs(x - cx) <= width * 0.09 and height * 0.12 <= y <= by
                    inside = d <= rad or neck
                    edge = (rad - bw <= d <= rad) or (neck and abs(abs(x - cx) - width * 0.09) < bw)
                if inside:
                    a = 255
                    if outline_only:
                        r, g, b = 255, 255, 255
                    elif edge:
                        r, g, b = br, bg, bb
                    else:
                        shade = 1.0 - 0.35 * (((x - cx) / width) + ((y - cy) / height))
                        shade = max(0.5, min(1.2, shade))
                        r, g, b = (min(255, int(c * shade)) for c in (fr, fg, fb))
            row += bytes((r, g, b, a))
        rows.append(bytes(row))
    raw = b"".join(rows)
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    png += _chunk(b"IDAT", zlib.compress(raw, 9))
    png += _chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
