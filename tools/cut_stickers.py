"""Cuts a sticker sheet (poses on a white background, in a grid) into transparent PNGs.

    python tools/cut_stickers.py brand/pino-sheet.png 4 2 site/img/pino name1 name2 ...

Needs Pillow. The white around each pose becomes transparent (only the white that touches the
edge, so the white in the eyes stays), then each pose is trimmed to its own size.
"""

import sys
from collections import deque

from PIL import Image


def _white(p) -> bool:
    return min(p[:3]) >= 236


def _pale_grey(p) -> bool:
    """The floor shadow: light and almost colourless."""
    return min(p[:3]) >= 165 and max(p[:3]) - min(p[:3]) <= 45


def _component(px, w, h, start, ok, seen) -> list:
    out, queue = [], deque([start])
    while queue:
        x, y = queue.popleft()
        i = y * w + x
        if seen[i] or not ok(px[x, y]):
            continue
        seen[i] = 1
        out.append((x, y))
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx]:
                queue.append((nx, ny))
    return out


def cut_out(img: Image.Image) -> Image.Image:
    """White background, the white caught between the legs and the floor shadow become transparent.
    The small white spots (the shine in the eyes) stay."""
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()
    seen = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            if seen[y * w + x] or not _white(px[x, y]):
                continue
            blob = _component(px, w, h, (x, y), _white, seen)
            touches = any(bx in (0, w - 1) or by in (0, h - 1) for bx, by in blob)
            if touches or len(blob) > 250:
                for bx, by in blob:
                    px[bx, by] = (255, 255, 255, 0)
    # The shadow under the feet: pale grey that touches what is already transparent.
    seen = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            p = px[x, y]
            if seen[y * w + x] or p[3] == 0 or not _pale_grey(p):
                continue
            blob = _component(px, w, h, (x, y), lambda q: q[3] and _pale_grey(q), seen)
            if len(blob) > 250:
                for bx, by in blob:
                    px[bx, by] = (255, 255, 255, 0)
    return img


def main() -> None:
    sheet, cols, rows, prefix, *names = sys.argv[1:]
    cols, rows = int(cols), int(rows)
    img = Image.open(sheet)
    cw, ch = img.width // cols, img.height // rows
    for n, name in enumerate(names):
        r, c = divmod(n, cols)
        cell = cut_out(img.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch)))
        box = cell.getbbox()
        if box:
            cell = cell.crop(box)
        cell.save(f"{prefix}-{name}.png", optimize=True)
        print(f"{prefix}-{name}.png", cell.size)


if __name__ == "__main__":
    main()
