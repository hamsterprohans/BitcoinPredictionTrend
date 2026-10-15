from app import config


def test_constants():
    assert config.SEQ_LEN == 20
    assert config.CLIP_VAL == 5.0
    assert config.HORIZONS == [1, 3, 5, 7, 15, 20, 25, 30, 35]
    assert config.MH_SEEDS == [47, 123, 2024]
    assert config.ARTIFACTS.name == "model_artifacts"
