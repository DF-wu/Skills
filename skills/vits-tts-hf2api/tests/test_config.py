import os

import vits_tts_hf2api.config as config


def test_defaults():
    assert config.BASE_URL == "https://ikechan8370-vits-uma-genshin-honkai.hf.space"
    assert (
        config.FALLBACK_BASE_URL == "https://zomehwh-vits-uma-genshin-honkai.hf.space"
    )
    assert config.HOST == "0.0.0.0"
    assert config.PORT == 80
    assert config.API_KEY is None
    assert config.DEFAULT_SPEAKER == "日语神里绫华（早见沙织）"
    # Default is "ja" (NOT "mix"): mix requires [ZH]/[JA] markers.
    assert config.DEFAULT_LANGUAGE == "ja"
    assert config.DEFAULT_NOISE_SCALE == 0.6
    assert config.DEFAULT_NOISE_SCALE_W == 0.668
    assert config.DEFAULT_LENGTH_SCALE == 1.2
    assert config.FN_INDEX == 0
    assert config.REQUEST_TIMEOUT == 120.0
    assert config.USER_AGENT == "Mozilla/5.0 AppleWebKit/537.36 Chrome/143 Safari/537"
    assert config.MAX_TEXT_LENGTH == 500
    assert config.FALLBACK_MAX_TEXT_LENGTH == 100


def test_env_override(monkeypatch):
    monkeypatch.setenv("BASE_URL", "https://example.com")
    monkeypatch.setenv("FALLBACK_BASE_URL", "https://fallback.example.com")
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "8080")
    monkeypatch.setenv("API_KEY", "secret")
    monkeypatch.setenv("DEFAULT_SPEAKER", "钟离")
    monkeypatch.setenv("DEFAULT_LANGUAGE", "ja")
    monkeypatch.setenv("DEFAULT_NOISE_SCALE", "0.5")
    monkeypatch.setenv("DEFAULT_NOISE_SCALE_W", "0.7")
    monkeypatch.setenv("DEFAULT_LENGTH_SCALE", "1.0")
    monkeypatch.setenv("FN_INDEX", "1")
    monkeypatch.setenv("REQUEST_TIMEOUT", "30")
    monkeypatch.setenv("MAX_TEXT_LENGTH", "200")
    monkeypatch.setenv("FALLBACK_MAX_TEXT_LENGTH", "50")

    import importlib
    import vits_tts_hf2api.config as cfg

    importlib.reload(cfg)

    assert cfg.BASE_URL == "https://example.com"
    assert cfg.FALLBACK_BASE_URL == "https://fallback.example.com"
    assert cfg.HOST == "127.0.0.1"
    assert cfg.PORT == 8080
    assert cfg.API_KEY == "secret"
    assert cfg.DEFAULT_SPEAKER == "钟离"
    assert cfg.DEFAULT_LANGUAGE == "ja"
    assert cfg.DEFAULT_NOISE_SCALE == 0.5
    assert cfg.DEFAULT_NOISE_SCALE_W == 0.7
    assert cfg.DEFAULT_LENGTH_SCALE == 1.0
    assert cfg.FN_INDEX == 1
    assert cfg.REQUEST_TIMEOUT == 30.0
    assert cfg.MAX_TEXT_LENGTH == 200
    assert cfg.FALLBACK_MAX_TEXT_LENGTH == 50

    importlib.reload(config)
