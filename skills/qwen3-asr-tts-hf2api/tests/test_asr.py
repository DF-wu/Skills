import pytest
from aiohttp import FormData
from unittest.mock import AsyncMock


async def test_asr_success(client, monkeypatch):
    async def mock_upload(session, base_url, file_bytes, filename, content_type=None):
        return "/tmp/upload.wav"

    async def mock_call_sse(session, base_url, api_name, data, timeout=300):
        return ["English", "Hello world", None, None]

    monkeypatch.setattr("qwen3_asr_tts_hf2api.gradio_sse.upload_file", mock_upload)
    monkeypatch.setattr("qwen3_asr_tts_hf2api.gradio_sse.call_gradio_sse", mock_call_sse)

    data = FormData()
    data.add_field("file", b"audio data", filename="test.wav")
    data.add_field("model", "qwen3-asr")
    resp = await client.post("/v1/audio/transcriptions", data=data)
    assert resp.status == 200
    result = await resp.json()
    assert result["text"] == "Hello world"


async def test_asr_error_null_503(client, monkeypatch):
    async def mock_upload(session, base_url, file_bytes, filename, content_type=None):
        return "/tmp/upload.wav"

    async def mock_call_sse(session, base_url, api_name, data, timeout=300):
        from qwen3_asr_tts_hf2api import gradio_sse
        raise gradio_sse.GradioApiError("null")

    monkeypatch.setattr("qwen3_asr_tts_hf2api.gradio_sse.upload_file", mock_upload)
    monkeypatch.setattr("qwen3_asr_tts_hf2api.gradio_sse.call_gradio_sse", mock_call_sse)

    data = FormData()
    data.add_field("file", b"audio data", filename="test.wav")
    resp = await client.post("/v1/audio/transcriptions", data=data)
    assert resp.status == 503
    result = await resp.json()
    assert "ASR upstream unavailable" in result["error"]


async def test_asr_missing_file(client):
    data = FormData()
    data.add_field("model", "qwen3-asr")
    resp = await client.post("/v1/audio/transcriptions", data=data)
    assert resp.status == 400


async def test_asr_with_language(client, monkeypatch):
    async def mock_upload(session, base_url, file_bytes, filename, content_type=None):
        return "/tmp/upload.wav"

    async def mock_call_sse(session, base_url, api_name, data, timeout=300):
        return ["English", "Hello", None, None]

    monkeypatch.setattr("qwen3_asr_tts_hf2api.gradio_sse.upload_file", mock_upload)
    monkeypatch.setattr("qwen3_asr_tts_hf2api.gradio_sse.call_gradio_sse", mock_call_sse)

    data = FormData()
    data.add_field("file", b"audio data", filename="test.wav")
    data.add_field("language", "en")
    resp = await client.post("/v1/audio/transcriptions", data=data)
    assert resp.status == 200
    result = await resp.json()
    assert result["text"] == "Hello"
    assert result["language"] == "English"
