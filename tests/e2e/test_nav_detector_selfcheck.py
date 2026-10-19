import pytest

from tests.e2e.test_accessibility_ui import SAME_ROW

pytestmark = pytest.mark.e2e


def test_wrap_detector_really_detects_a_wrapped_link(page, server):
    """Pemeriksa SAME_ROW harus gagal bila satu tautan terpotong; jika tidak, tes lain tak berarti."""
    page.goto(server + "/tentang")
    assert page.evaluate(SAME_ROW) is True
    page.add_style_tag(content="#main-nav a{white-space:normal!important} #main-nav a:nth-child(2){width:50px}")
    assert page.evaluate(SAME_ROW) is False
