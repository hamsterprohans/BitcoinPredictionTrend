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


def test_profile_photo_keeps_white_background_in_card():
    data = (S / "img" / "foto-hans.png").read_bytes()
    assert struct.unpack(">B", data[25:26])[0] == 2                 # RGB tanpa alfa: latar putih asli
    rule = (S / "css" / "app.css").read_text().split(".about-photo{", 1)[1].split("}", 1)[0]
    assert "background:#fff" in rule


def test_app_config_has_supabase_url_and_only_a_publishable_key():
    import re
    text = (S / "js" / "app-config.js").read_text()
    assert re.search(r'supabaseUrl: "https://[a-z0-9]{20}\.supabase\.co"', text)
    assert re.search(r'supabaseAnonKey: "sb_publishable_[A-Za-z0-9_-]{20,}"', text)
    assert "sb_secret" not in text and "service_role" not in text and "eyJ" not in text
