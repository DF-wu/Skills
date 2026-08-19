import vits_tts_hf2api.speakers as speakers


def test_exact_match():
    assert speakers.resolve_speaker("派蒙") == 0
    assert speakers.resolve_speaker("钟离") == 23
    assert speakers.resolve_speaker("三月七") == 100


def test_case_insensitive():
    assert speakers.resolve_speaker("paimon") == 0
    assert speakers.resolve_speaker("ZHONGLI") == 23
    assert speakers.resolve_speaker("Keqing") == 21


def test_alias_resolution():
    assert speakers.resolve_speaker("paimon") == 0
    assert speakers.resolve_speaker("raiden") == 33
    assert speakers.resolve_speaker("kafka") == 104
    assert speakers.resolve_speaker("specialweek") == 200


def test_unknown_fallback():
    assert speakers.resolve_speaker("不存在的角色") == speakers.SPEAKERS["派蒙"]
    assert speakers.resolve_speaker("") == speakers.SPEAKERS["派蒙"]
    assert speakers.resolve_speaker(None) == speakers.SPEAKERS["派蒙"]


def test_search_exact():
    results = speakers.search_speakers("派蒙")
    assert any(r["name"] == "派蒙" for r in results)


def test_search_substring():
    results = speakers.search_speakers("钟")
    assert any(r["name"] == "钟离" for r in results)


def test_search_alias():
    results = speakers.search_speakers("paimon")
    assert any(r["name"] == "派蒙" for r in results)


def test_search_no_duplicate_ids():
    results = speakers.search_speakers("march")
    ids = [r["id"] for r in results]
    assert len(ids) == len(set(ids))


def test_languages():
    assert speakers.LANGUAGES["zh"] == "中文"
    assert speakers.LANGUAGES["ja"] == "日语"
    assert "mix" in speakers.LANGUAGES
