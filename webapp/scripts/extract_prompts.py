"""Ekstrak 3 prompt sentimen dari notebook (10) ke app/prompts.py (teks identik).

Pemakaian: python scripts/extract_prompts.py "<path notebook .ipynb>"
"""
import json
import re
import sys
from pathlib import Path

DEFS = {
    "pemahaman": r"def get_sentiment_score_pemahaman\w*\(",
    "detail": r"def get_sentiment_score_detail\w*\(",
    "bullbear": r"def get_sentiment_score_bullbear\w*\(",
}


def extract(nb_path: str) -> dict:
    nb = json.loads(Path(nb_path).read_text(encoding="utf-8"))
    out = {}
    for kind, pat in DEFS.items():
        found = []
        for cell in nb["cells"]:
            if cell["cell_type"] != "code":
                continue
            src = "".join(cell["source"])
            m = re.search(pat, src)
            if not m:
                continue
            p = re.search(r'prompt = f"""(.*?)"""', src[m.end():], re.S)
            found.append(p.group(1))
        assert len(found) == 1, f"{kind}: ditemukan {len(found)} definisi, harus 1"
        text = found[0]
        assert text.count("{combined}") == 1, f"{kind}: harus ada tepat satu {{combined}}"
        assert "{" not in text.replace("{combined}", ""), f"{kind}: ada kurung kurawal lain"
        assert "\\" not in text, f"{kind}: ada backslash, periksa manual"
        out[kind] = text
    return out


def main():
    prompts = extract(sys.argv[1])
    target = Path(__file__).resolve().parents[1] / "app" / "prompts.py"
    lines = ['"""DIHASILKAN oleh scripts/extract_prompts.py dari notebook (10). Jangan edit manual."""', "PROMPTS = {"]
    for k, v in prompts.items():
        lines.append(f"    {k!r}: {v!r},")
    lines.append("}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"ditulis: {target}")


if __name__ == "__main__":
    main()
