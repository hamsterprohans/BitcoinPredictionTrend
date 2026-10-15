import numpy as np
import pytest

from app.explain import (build_facts, feature_rows, generate_narrative, rank_contributions, template_narrative,
                         validate)
from app.inference import FEATURE_ORDER


def _facts():
    stats = {"quantiles": {f: np.round(np.linspace(0, 10, 101), 6).tolist() for f in FEATURE_ORDER}}
    deltas = np.zeros(13)
    deltas[FEATURE_ORDER.index("Vol_30")], deltas[FEATURE_ORDER.index("RSI14")] = 3.24, -2.1
    deltas[FEATURE_ORDER.index("MACD")] = 1.05
    rec = {"date": "2026-02-16", "target_date": "2026-02-17", "prob": 0.5193, "threshold": 0.4557, "level": "tinggi",
           "features": feature_rows({f: 5.0 for f in FEATURE_ORDER}, stats), "contributions": rank_contributions(deltas)}
    return build_facts(rec, auc=0.52)


FACTS = _facts()
GOOD = template_narrative(FACTS)


def test_template_passes_every_check_by_construction():
    assert validate(GOOD, FACTS) == []
    assert 40 <= len(GOOD.split()) <= 170
    assert "belum terbukti lebih baik dari tebakan acak" in GOOD.lower() and "bukan saran investasi" in GOOD.lower()


@pytest.mark.parametrize("mutate,expected", [
    (lambda t: t.replace("16 Februari 2026", "17 Maret 2026"), "tanggal_valid"),
    (lambda t: t + " Peluangnya 87%.", "angka_valid"),
    (lambda t: t.replace("0,5193", "nilai tertentu"), "skor_disebut"),
    (lambda t: t.replace("prediksinya naik", "prediksinya turun"), "label_benar"),
    (lambda t: t.replace("Volatilitas 30 hari", "satu hal").replace("RSI 14 hari", "hal lain"), "fitur_disebut"),
    (lambda t: t + " Sebaiknya beli sekarang.", "kata_terlarang"),
    (lambda t: t.replace("Ini bukan saran investasi.", ""), "disclaimer"),
    (lambda t: t.replace("belum terbukti lebih baik dari tebakan acak", "cukup baik"), "keterbatasan"),
    (lambda t: t.replace("tidak pasti dan bisa keliru", "perlu dibaca hati-hati"), "ketidakpastian"),
    (lambda t: "Terlalu pendek.", "panjang"),
    (lambda t: t + " " + "kata " * 200, "panjang"),
])
def test_each_validator_rule_catches_its_violation(mutate, expected):
    assert expected in validate(mutate(GOOD), FACTS)


def test_tidak_pasti_is_not_flagged_as_forbidden_word():
    assert "kata_terlarang" not in validate(GOOD, FACTS)       # "tidak pasti" boleh, "pasti" sendirian tidak


class _Resp:
    def __init__(self, text):
        self.content = [type("B", (), {"text": text})()]


class FakeLLM:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return _Resp(r)


def test_generate_retries_with_feedback_then_succeeds():
    llm = FakeLLM(["Teks pendek.", GOOD])
    out = generate_narrative(llm, FACTS)
    assert out["source"] == "llm" and out["attempts"] == 2 and out["text"] == GOOD and out["temperature"] == 0.1
    assert llm.calls[0]["temperature"] == 0.1 and llm.calls[0]["model"] == "claude-haiku-4-5"
    assert "PERBAIKI" in llm.calls[1]["messages"][0]["content"] and "panjang" in llm.calls[1]["messages"][0]["content"]
    assert "0,5193" in llm.calls[0]["messages"][0]["content"]               # blok fakta dikirim


def test_generate_falls_back_to_template_after_three_invalid():
    llm = FakeLLM(["salah", "salah lagi", "tetap salah"])
    out = generate_narrative(llm, FACTS)
    assert out["source"] == "template" and out["text"] == template_narrative(FACTS) and len(llm.calls) == 3


def test_generate_retries_without_temperature_when_api_rejects_it():
    llm = FakeLLM([RuntimeError("`temperature` is not supported for this model"), GOOD])
    out = generate_narrative(llm, FACTS)
    assert out["source"] == "llm" and out["temperature"] is None
    assert "temperature" in llm.calls[0] and "temperature" not in llm.calls[1]


def test_generate_survives_api_errors_and_never_returns_unvalidated_text():
    llm = FakeLLM([RuntimeError("500"), RuntimeError("500"), RuntimeError("500")])
    out = generate_narrative(llm, FACTS)
    assert out["source"] == "template" and validate(out["text"], FACTS) == []


@pytest.mark.parametrize("mutate,expected", [
    (lambda t: t.replace("probabilitas naik 0,5193 terhadap ambang keputusan 0,4557",
                         "probabilitas naik 0,4557 terhadap ambang keputusan 0,5193"), "skor_disebut"),
    (lambda t: t.replace("(-2,1 poin", "(+2,1 poin"), "tanda_pengaruh"),
    (lambda t: t + " Namun harga diperkirakan akan turun.", "label_benar"),
    (lambda t: t.replace("prediksinya naik", "prediksinya bukan naik, melainkan turun"), "label_benar"),
    (lambda t: t + " Pembelian aset ini wajar.", "kata_terlarang"),
    (lambda t: t + " Penjualan bisa dipertimbangkan.", "kata_terlarang"),
    (lambda t: t + " Ambil posisi hold.", "kata_terlarang"),
    (lambda t: t + " Disarankan menunggu.", "kata_terlarang"),
    (lambda t: t + " Harga naik karena RSI.", "kata_terlarang"),
    (lambda t: t + " Peluangnya lima puluh persen.", "angka_valid"),
    (lambda t: t + " Pada 17 Oktober harga bergerak.", "tanggal_valid"),
    (lambda t: "Tidak benar bahwa model belum terbukti lebih baik dari tebakan acak. "
               + t.replace("Model belum terbukti lebih baik dari tebakan acak", "Model cukup baik"), "keterbatasan"),
    (lambda t: t.replace("Ini bukan saran investasi.", "Kami tidak bilang ini bukan saran investasi."), "disclaimer"),
])
def test_validator_catches_lenient_cases_found_in_review(mutate, expected):
    assert expected in validate(mutate(GOOD), FACTS)


def test_feature_mention_counts_whole_labels_only():
    # "Sinyal MACD" tidak boleh sekaligus dihitung sebagai "MACD"
    stats = {"quantiles": {f: np.round(np.linspace(0, 10, 101), 6).tolist() for f in FEATURE_ORDER}}
    deltas = np.zeros(13)
    deltas[FEATURE_ORDER.index("MACD")], deltas[FEATURE_ORDER.index("MACD_Signal")] = 3.0, 2.0
    deltas[FEATURE_ORDER.index("RSI14")] = 1.0
    rec = {"date": "2026-02-16", "target_date": "2026-02-17", "prob": 0.5193, "threshold": 0.4557, "level": "tinggi",
           "features": feature_rows({f: 5.0 for f in FEATURE_ORDER}, stats), "contributions": rank_contributions(deltas)}
    f = build_facts(rec)
    text = template_narrative(f)
    only_signal = text.replace("MACD (+3,0", "hal").replace("RSI 14 hari", "hal lain")        # hanya "Sinyal MACD" yang tersisa
    assert "fitur_disebut" in validate(only_signal, f)


def test_unicode_minus_in_delta_is_accepted_as_the_same_sign():
    assert validate(GOOD.replace("(-2,1 poin", "(−2,1 poin"), FACTS) == []
    assert "tanda_pengaruh" in validate(GOOD.replace("(-2,1 poin", "(+2,1 poin"), FACTS)           # tanda salah tetap ditolak


def test_counting_features_is_fine_but_quantity_words_are_not():
    assert "angka_valid" not in validate(GOOD + " Tiga fitur teratas disebut.", FACTS)
    for bad in (" Peluangnya dua persen.", " Peluangnya lima puluh persen.", " Naik tiga poin.", " Sekitar sepuluh kali."):
        assert "angka_valid" in validate(GOOD + bad, FACTS), bad


def test_day_month_without_year_is_allowed_only_for_the_facts_dates():
    assert "tanggal_valid" not in validate(GOOD + " Berdasarkan data hingga 16 Februari.", FACTS)
    assert "tanggal_valid" not in validate(GOOD + " Target 17 Februari.", FACTS)
    assert "tanggal_valid" in validate(GOOD + " Pada 17 Oktober harga bergerak.", FACTS)
    assert "tanggal_valid" in validate(GOOD + " Pada 18 Februari harga bergerak.", FACTS)


class _ApiStatusError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg)
        self.status_code = status


def test_billing_and_auth_errors_abort_instead_of_silently_writing_templates():
    from app.explain import FatalAPIError
    for err in (RuntimeError("Error code: 400 - Your credit balance is too low to access the Anthropic API."),
                _ApiStatusError(401, "invalid x-api-key"), _ApiStatusError(403, "forbidden")):
        with pytest.raises(FatalAPIError):
            generate_narrative(FakeLLM([err]), FACTS)
    out = generate_narrative(FakeLLM([RuntimeError("500 server error")] * 3), FACTS)      # galat sementara tetap cadangan template
    assert out["source"] == "template"


def test_feature_without_stated_influence_is_fine_but_a_wrong_sign_is_not():
    import re
    no_deltas = re.sub(r"\s\([+-]\d+,\d poin persentase\)", "", GOOD)
    assert no_deltas != GOOD and "tanda_pengaruh" not in validate(no_deltas, FACTS)       # menyebut fitur tanpa angka pengaruh: wajar
    assert validate(no_deltas, FACTS) == []
    assert "tanda_pengaruh" in validate(GOOD.replace("(+3,2 poin", "(-3,2 poin"), FACTS)   # angka disebut dengan tanda terbalik: ditolak
