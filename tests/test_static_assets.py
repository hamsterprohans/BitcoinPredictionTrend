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
