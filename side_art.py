"""The picture on the right of the launcher and the scene tester, and their window icon.

No game art ships with the program. Both are cut at run time from the player's own 2005
Fate/hollow ataraxia files and kept in %LOCALAPPDATA%\\FHARestoration\\art:
  * the picture: bh02, the opening CG of Rin's Eclipse scene, cropped to her face and sweater so
    nothing explicit shows;
  * the window/taskbar icon: Caren's face from her habit sprite (the one Caren V uses most), in a
    round badge.
Until the 2005 folder is known, the launcher's own icon art stands in. (The .exe file's own icon
is part of the download, so it stays the original design.)
"""
import os
import sys
import zlib

HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "FHARestoration")
PICTURE_CACHE = os.path.join(WORK, "art", "side_rin.png")
ICON_CACHE = os.path.join(WORK, "art", "icon_caren.png")
BG_ARCHIVES = ("patch3.xp3", "patch2.xp3", "patch.xp3", "bgimage.xp3")   # first match wins
FG_ARCHIVES = ("patch3.xp3", "patch2.xp3", "patch.xp3", "fgimage.xp3")
PICTURE_SOURCE, PICTURE_SIZE = "bh02", (800, 600)
# the part of the CG that may be shown: her head and sweater, above the hem (y < 395 everywhere)
SAFE = (0, 0, 400, 392)
FOCUS_X = 202                         # centre of her face
ICON_SOURCE, ICON_SIZE = "カレン修道服無帽04b(中)", (264, 519)
ICON_FACE = (52, 4, 212, 164)         # a square around her head
ICON_SIZES = (256, 64, 48, 32, 16)
SKIP_DIRS = ("censored_h/", "censored_mature/", "decensored/")


def _fhar():
    d = os.path.join(HERE, "fhar")
    if d not in sys.path:
        sys.path.insert(0, d)


def _read_source(fan, stem, archives, mode="RGB"):
    """One picture from the 2005 archives as a PIL image, or None."""
    _fhar()
    import tlg
    import xp3
    from cxdec import Cxdec
    cx = None
    for arc in archives:
        path = os.path.join(fan, arc)
        if not os.path.exists(path):
            continue
        for e in xp3.entries(path):
            name = e["name"].replace("\\", "/").lower()
            if name.startswith(SKIP_DIRS) or os.path.basename(name) != stem.lower() + ".tlg":
                continue
            raw = bytearray()
            with open(path, "rb") as f:
                for flags, off, _, packed in e["segments"]:
                    f.seek(off)
                    b = f.read(packed)
                    raw += zlib.decompress(b) if flags & 7 == 1 else b
            raw = bytes(raw)
            if zlib.adler32(raw) != e.get("adler"):
                cx = cx or Cxdec.from_filter_script(os.path.join(fan, "Android", "xp3filter.tjs"))
                raw = cx.decrypt(e.get("adler", 0), 0, raw)
                if zlib.adler32(raw) != e.get("adler"):
                    return None
            return tlg.to_pil(raw).convert(mode)
    return None


def _cached(fan, cache, make):
    """A picture from the cache, or made from the 2005 files by make(fan) and then cached."""
    from PIL import Image
    try:
        return Image.open(cache).convert("RGBA")
    except (OSError, ValueError):
        pass
    if not fan:
        return None
    try:
        im = make(fan)
    except Exception:  # noqa: BLE001  (an unreadable archive: the stand-in is shown)
        return None
    if im is None:
        return None
    try:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        im.save(cache)
    except OSError:
        pass
    return im


def _rin(fan):
    im = _read_source(fan, PICTURE_SOURCE, BG_ARCHIVES)
    return im.crop(SAFE) if im is not None and im.size == PICTURE_SIZE else None


def _fit(src, w, h):
    """Fill w x h from the safe area: full height, width centred on her face."""
    from PIL import Image
    sw, sh = src.size
    cw = min(sw, round(sh * w / h))
    ch = sh if cw < sw else min(sh, round(sw * h / w))
    x0 = max(0, min(sw - cw, FOCUS_X - cw // 2))
    return src.crop((x0, 0, x0 + cw, ch)).resize((w, h), Image.LANCZOS).convert("RGB")


def stand_in(w, h):
    """The launcher's own art on a dark indigo gradient."""
    from PIL import Image
    top, bottom = (36, 28, 72), (18, 14, 38)
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        t = y / max(1, h - 1)
        c = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
        for x in range(w):
            px[x, y] = c
    try:
        icon = Image.open(os.path.join(HERE, "assets", "launcher.png")).convert("RGBA")
        s = round(w * 0.62)
        icon = icon.resize((s, s), Image.LANCZOS)
        im.paste(icon, ((w - s) // 2, (h - s) // 2 - h // 12), icon)
    except OSError:
        pass
    return im


def picture(fan, w, h):
    """(PIL image of w x h, True if it is the 2005 picture)."""
    src = _cached(fan, PICTURE_CACHE, _rin)
    return (_fit(src, w, h), True) if src is not None else (stand_in(w, h), False)


def _badge(face, size):
    """A face in a circle with a thin gold ring, on transparency (drawn 4x, then reduced)."""
    from PIL import Image, ImageDraw
    big = size * 4
    out = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ring = max(4, big // 22)
    d = ImageDraw.Draw(out)
    d.ellipse((0, 0, big - 1, big - 1), fill=(214, 168, 74, 255))                   # gold ring
    d.ellipse((ring, ring, big - 1 - ring, big - 1 - ring), fill=(28, 30, 64, 255))  # navy behind her
    inner = big - 2 * ring
    mask = Image.new("L", (inner, inner), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, inner - 1, inner - 1), fill=255)
    f = face.resize((inner, inner), Image.LANCZOS)
    a = Image.composite(f.getchannel("A"), Image.new("L", f.size, 0), mask)
    f.putalpha(a)
    out.alpha_composite(f, (ring, ring))
    return out.resize((size, size), Image.LANCZOS)


def _caren(fan):
    sprite = _read_source(fan, ICON_SOURCE, FG_ARCHIVES, "RGBA")
    return _badge(sprite.crop(ICON_FACE), ICON_SIZES[0]) if sprite is not None and sprite.size == ICON_SIZE else None


def icon_images(fan):
    """Caren's face badge in ICON_SIZES (largest first), or None while the 2005 folder is unknown."""
    from PIL import Image
    big = _cached(fan, ICON_CACHE, _caren)
    if big is None:
        return None
    return [big if s == ICON_SIZES[0] else big.resize((s, s), Image.LANCZOS) for s in ICON_SIZES]


def icon_file(fan, path=None):
    """Caren's face badge as a Windows .ico (for a shortcut), written next to the other cut art
    unless path is given. Returns its path, or None while the 2005 folder is unknown."""
    ims = icon_images(fan)
    if not ims:
        return None
    path = path or os.path.join(os.path.dirname(ICON_CACHE), "icon_caren.ico")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        ims[0].save(path, format="ICO", sizes=[(s, s) for s in ICON_SIZES])
    except OSError:
        return None
    return path
