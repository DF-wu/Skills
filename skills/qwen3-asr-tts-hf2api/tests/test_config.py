import os

from qwen3_asr_tts_hf2api import config


def test_config_defaults():
    assert config.TTS_BASE_URL == "https://qwen-qwen3-tts-demo.hf.space"
    assert config.ASR_BASE_URL == "https://qwen-qwen3-asr.hf.space"
    assert config.HOST == "0.0.0.0"
    assert config.PORT == 80
    assert config.API_KEY is None
    assert config.DEFAULT_VOICE == "cherry"
    assert config.DEFAULT_LANGUAGE == "auto"
    assert config.REQUEST_TIMEOUT == 300.0
    assert config.USER_AGENT == "Mozilla/5.0 AppleWebKit/537.36 Chrome/143 Safari/537"


def test_config_env_override(monkeypatch):
    monkeypatch.setenv("TTS_BASE_URL", "https://custom-tts.hf.space")
    monkeypatch.setenv("ASR_BASE_URL", "https://custom-asr.hf.space")
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "8080")
    monkeypatch.setenv("API_KEY", "secret123")
    monkeypatch.setenv("DEFAULT_VOICE", "adam")
    monkeypatch.setenv("DEFAULT_LANGUAGE", "zh")
    monkeypatch.setenv("REQUEST_TIMEOUT", "60")

    import importlib
    import qwen3_asr_tts_hf2api.config as config_mod

    importlib.reload(config_mod)
    assert config_mod.TTS_BASE_URL == "https://custom-tts.hf.space"
    assert config_mod.ASR_BASE_URL == "https://custom-asr.hf.space"
    assert config_mod.HOST == "127.0.0.1"
    assert config_mod.PORT == 8080
    assert config_mod.API_KEY == "secret123"
    assert config_mod.DEFAULT_VOICE == "adam"
    assert config_mod.DEFAULT_LANGUAGE == "zh"
    assert config_mod.REQUEST_TIMEOUT == 60.0

    importlib.reload(config_mod)

    monkeypatch.delenv("TTS_BASE_URL")
    monkeypatch.delenv("ASR_BASE_URL")
    monkeypatch.delenv("HOST")
    monkeypatch.delenv("PORT")
    monkeypatch.delenv("API_KEY")
    monkeypatch.delenv("DEFAULT_VOICE")
    monkeypatch.delenv("DEFAULT_LANGUAGE")
    monkeypatch.delenv("REQUEST_TIMEOUT")
    importlib.reload(config_mod)
