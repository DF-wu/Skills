import pytest

from qwen3_asr_tts_hf2api import models


class TestResolveVoice:
    def test_exact_match(self):
        assert models.resolve_voice("vivian") == "Vivian / 十三"
        assert models.resolve_voice("VIVIAN") == "Vivian / 十三"
        assert models.resolve_voice("Ethan") == "Ethan / 晨煦"

    def test_alias(self):
        assert models.resolve_voice("alloy") == "Vivian / 十三"
        assert models.resolve_voice("echo") == "Ethan / 晨煦"
        assert models.resolve_voice("fable") == "Momo / 茉兔"
        assert models.resolve_voice("onyx") == "Kai / 凯"
        assert models.resolve_voice("nova") == "Chelsie / 千雪"
        assert models.resolve_voice("shimmer") == "Serena / 苏瑶"

    def test_unknown_fallback(self):
        assert models.resolve_voice("unknown_voice") == "Cherry / 芊悦"
        assert models.resolve_voice("") == "Cherry / 芊悦"


class TestResolveLanguage:
    def test_tts_exact(self):
        assert models.resolve_language("zh", target="tts") == "Chinese / 中文"
        assert models.resolve_language("EN", target="tts") == "English / 英文"
        assert models.resolve_language("auto", target="tts") == "Auto / 自动"

    def test_asr_exact(self):
        assert models.resolve_language("zh", target="asr") == "Chinese"
        assert models.resolve_language("AR", target="asr") == "Arabic"
        assert models.resolve_language("mk", target="asr") == "Macedonian"

    def test_unknown_fallback(self):
        assert models.resolve_language("xx", target="tts") == "Auto / 自动"
        assert models.resolve_language("zz", target="asr") == "Auto"


class TestDataCompleteness:
    def test_tts_voices_count(self):
        assert len(models.TTS_VOICES) == 49

    def test_tts_languages_count(self):
        assert len(models.TTS_LANGUAGES) == 11

    def test_asr_languages_count(self):
        assert len(models.ASR_LANGUAGES) == 31

    def test_aliases_count(self):
        assert len(models.VOICE_ALIASES) == 6

    def test_voice_keys_lowercase(self):
        for key in models.TTS_VOICES:
            assert key == key.lower()
