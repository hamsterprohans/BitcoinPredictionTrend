import struct
from app import config

S = config.STATIC_DIR


def test_fonts_are_woff2():
    for name in ("Geist-Variable.woff2", "GeistMono-Variable.woff2"):
        data = (S / "fonts" / name).read_bytes()
        assert data[:4] == b"wOF2" and len(data) > 20_000, name


def test_vendor_files_present():
    assert (S / "vendor" / "three.module.min.js").stat().st_size > 100_000
    assert (S / "vendor" / "lightweight-charts.standalone.production.js").stat().st_size > 50_000


def test_tokens_declare_geist_and_palette():
    css = (S / "css" / "tokens.css").read_text()
    assert '"Geist"' in css and '"Geist Mono"' in css
    for token in ("--bg:#0d0c0a", "--gold:#e6c068", "--up:#35c08a", "--down:#ef6a5e"):
        assert token in css.replace(" ", ""), token


def test_css_braces_balanced_and_no_orphan_keyframe_steps():
    import re
    for name in ("app.css", "tokens.css"):
        css = (S / "css" / name).read_text()
        assert css.count("{") == css.count("}"), name
        assert not re.search(r"^(from|to|\d+%)\s*\{", css, re.M), name   # langkah keyframes harus di dalam @keyframes


def test_main_focus_ring_removed_rule_present():
    assert "main:focus{outline:none}" in (S / "css" / "app.css").read_text().replace(" ", "")


def test_profile_photo_is_a_png():
    data = (S / "img" / "foto-hans.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and 10_000 < len(data) < 500_000


def test_profile_photo_has_transparent_background():
    data = (S / "img" / "foto-hans.png").read_bytes()
    width, height, depth, color_type = struct.unpack(">IIBB", data[16:26])
    assert color_type == 6 and depth == 8                      # RGBA
    px = _decode_rgba(data, width, height)
    for x, y in [(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1), (width // 2, 0)]:
        assert px[y][x][3] == 0, (x, y)                          # sudut/tepi atas transparan
    assert px[height // 2][width // 2][3] == 255                 # subjek tetap buram


def test_profile_photo_css_has_no_white_box():
    css = (S / "css" / "app.css").read_text()
    rule = css.split(".about-photo{", 1)[1].split("}", 1)[0]
    assert "#fff" not in rule and "background:#" not in rule


def _decode_rgba(data, width, height):
    import zlib
    pos, idat = 8, b""
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        if kind == b"IDAT":
            idat += data[pos + 8:pos + 8 + n]
        pos += 12 + n
    raw, bpp, stride = zlib.decompress(idat), 4, width * 4
    rows, prev = [], bytearray(stride)
    for y in range(height):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b, c = prev[i], (prev[i - bpp] if i >= bpp else 0)
            if f == 1: line[i] = (line[i] + a) & 255
            elif f == 2: line[i] = (line[i] + b) & 255
            elif f == 3: line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append([tuple(line[x * 4:x * 4 + 4]) for x in range(width)])
        prev = line
    return rows
