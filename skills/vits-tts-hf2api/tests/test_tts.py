import json
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web

from vits_tts_hf2api import config, rest_client, speakers


@pytest.fixture(autouse=True)
def reset_config(monkeypatch):
    monkeypatch.setattr(config, "API_KEY", None)
    monkeypatch.setattr(config, "BASE_URL", "https://primary.example.com")
    monkeypatch.setattr(
        config,
        "BACKUP_REST_URLS",
        ["https://backup1.example.com", "https://backup2.example.com"],
    )
    monkeypatch.setattr(config, "FALLBACK_WS_URL", "https://ws-fallback.example.com")
    monkeypatch.setattr(config, "VITS_MODELS_URL", "https://models.example.com")
    monkeypatch.setattr(config, "FN_INDEX", 0)
    monkeypatch.setattr(config, "REQUEST_TIMEOUT", 10)
    monkeypatch.setattr(config, "MAX_RETRIES", 3)
    monkeypatch.setattr(config, "MAX_TEXT_LENGTH", 500)
    monkeypatch.setattr(config, "FALLBACK_MAX_TEXT_LENGTH", 100)
    monkeypatch.setattr(config, "RETRY_DELAY", 0.0)
    monkeypatch.setattr(config, "DEFAULT_SPEAKER", "派蒙")
    monkeypatch.setattr(config, "DEFAULT_LANGUAGE", "mix")
    monkeypatch.setattr(config, "DEFAULT_NOISE_SCALE", 0.6)
    monkeypatch.setattr(config, "DEFAULT_NOISE_SCALE_W", 0.668)
    monkeypatch.setattr(config, "DEFAULT_LENGTH_SCALE", 1.2)


@pytest.fixture
def mock_rest():
    with patch("vits_tts_hf2api.tts.retry") as m:
        m.call_gradio_rest_with_retry = AsyncMock(return_value=b"wavbytes")
        m.is_retriable_rest_error = lambda e: True
        yield m


@pytest.fixture
def mock_rest_retriable_fail():
    with patch("vits_tts_hf2api.tts.retry") as m:
        err = rest_client.GradioRESTError("Server error", status_code=503)
        m.call_gradio_rest_with_retry = AsyncMock(side_effect=err)
        m.is_retriable_rest_error = lambda e: True
        yield m


@pytest.fixture
def mock_rest_non_retriable_fail():
    with patch("vits_tts_hf2api.tts.retry") as m:
        err = rest_client.GradioRESTError("Bad request", status_code=400)
        m.call_gradio_rest_with_retry = AsyncMock(side_effect=err)
        m.is_retriable_rest_error = lambda e: False
        yield m


@pytest.fixture
def mock_ws():
    with patch("vits_tts_hf2api.tts.ws_client") as m:
        m.call_gradio_ws = AsyncMock(return_value=[{"path": "/tmp/out.wav"}])
        m.download_result = AsyncMock(return_value=b"ws-wavbytes")
        m.GradioWSError = Exception
        yield m


async def test_speech_success_rest(cli, mock_rest):
    resp = await cli.post("/v1/audio/speech", json={"input": "你好", "voice": "派蒙"})
    assert resp.status == 200
    assert resp.content_type == "audio/wav"
    body = await resp.read()
    assert body == b"wavbytes"
    mock_rest.call_gradio_rest_with_retry.assert_awaited_once()
    args = mock_rest.call_gradio_rest_with_retry.call_args[0]
    assert args[1] == ["你好", speakers.LANGUAGES["mix"], "派蒙", 0.6, 0.668, 1.2]


async def test_speech_ws_fallback(cli, mock_rest_retriable_fail, mock_ws):
    resp = await cli.post("/v1/audio/speech", json={"input": "你好", "voice": "派蒙"})
    assert resp.status == 200
    body = await resp.read()
    assert body == b"ws-wavbytes"
    mock_ws.call_gradio_ws.assert_awaited_once()
    args = mock_ws.call_gradio_ws.call_args[0]
    assert args[0] == "https://ws-fallback.example.com"


async def test_speech_non_retriable_502(cli, mock_rest_non_retriable_fail):
    resp = await cli.post("/v1/audio/speech", json={"input": "hello", "voice": "派蒙"})
    assert resp.status == 502


async def test_speech_text_truncation(cli, mock_rest):
    long_text = "a" * 600
    resp = await cli.post("/v1/audio/speech", json={"input": long_text})
    assert resp.status == 200
    assert resp.headers.get("X-Warning") == "text-truncated"
    args = mock_rest.call_gradio_rest_with_retry.call_args[0]
    assert len(args[1][0]) == 500


async def test_speech_speed_mapping(cli, mock_rest):
    resp = await cli.post("/v1/audio/speech", json={"input": "hello", "speed": 2.0})
    assert resp.status == 200
    args = mock_rest.call_gradio_rest_with_retry.call_args[0]
    assert args[1][5] == 0.5


async def test_speech_unknown_speaker(cli, mock_rest):
    resp = await cli.post(
        "/v1/audio/speech", json={"input": "hello", "voice": "no_such_character"}
    )
    assert resp.status == 200
    args = mock_rest.call_gradio_rest_with_retry.call_args[0]
    assert args[1][2] == "no_such_character"


async def test_speech_cors_headers(cli, mock_rest):
    resp = await cli.post("/v1/audio/speech", json={"input": "hello"})
    assert resp.status == 200
    assert resp.headers.get("Access-Control-Allow-Origin") == "*"
    assert "POST" in resp.headers.get("Access-Control-Allow-Methods", "")


async def test_speech_auth_denied(cli, monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "secret123")
    resp = await cli.post(
        "/v1/audio/speech",
        json={"input": "hello"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status == 401


async def test_speech_auth_allowed(cli, mock_rest, monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "secret123")
    resp = await cli.post(
        "/v1/audio/speech",
        json={"input": "hello"},
        headers={"Authorization": "Bearer secret123"},
    )
    assert resp.status == 200


async def test_speech_format_warning(cli, mock_rest):
    resp = await cli.post(
        "/v1/audio/speech", json={"input": "hello", "response_format": "mp3"}
    )
    assert resp.status == 200
    assert resp.headers.get("X-Warning") == "format-conversion-not-supported"


async def test_speech_invalid_json(cli):
    resp = await cli.post(
        "/v1/audio/speech",
        data="not json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 400


async def test_speech_empty_input(cli):
    resp = await cli.post("/v1/audio/speech", json={"input": ""})
    assert resp.status == 400


async def test_vits_models_routing(cli):
    with patch("vits_tts_hf2api.tts.rest_client") as m:
        m.call_gradio_rest = AsyncMock(return_value=b"vits-models-wav")
        m.GradioRESTError = rest_client.GradioRESTError
        resp = await cli.post(
            "/v1/audio/speech", json={"input": "おはよう", "voice": "ayaka-jp"}
        )
        assert resp.status == 200
        body = await resp.read()
        assert body == b"vits-models-wav"
        m.call_gradio_rest.assert_awaited_once()
        call_args = m.call_gradio_rest.call_args
        assert call_args[0][1] == "https://models.example.com"
        assert call_args[1]["fn_index"] == 0


async def test_vits_models_error_502(cli):
    with patch("vits_tts_hf2api.tts.rest_client") as m:
        m.call_gradio_rest = AsyncMock(
            side_effect=rest_client.GradioRESTError(
                "Models Space error", status_code=503
            )
        )
        m.GradioRESTError = rest_client.GradioRESTError
        resp = await cli.post(
            "/v1/audio/speech", json={"input": "test", "voice": "ayaka-jp"}
        )
        assert resp.status == 502


async def test_get_models(cli):
    resp = await cli.get("/v1/models")
    assert resp.status == 200
    data = await resp.json()
    assert data["data"][0]["id"] == "vits-uma-genshin-honkai"
    assert "speakers" in data
    assert "languages" in data


async def test_get_models_search(cli):
    resp = await cli.get("/v1/models?search=派蒙")
    assert resp.status == 200
    data = await resp.json()
    assert any(s["name"] == "派蒙" for s in data["speakers"])
