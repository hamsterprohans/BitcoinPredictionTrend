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
