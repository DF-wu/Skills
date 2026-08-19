from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import FormData

from qwen3_asr_tts_hf2api import create_app


@pytest.fixture
async def client_with_auth(aiohttp_client, monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-key")
    import importlib
    from qwen3_asr_tts_hf2api import config

    importlib.reload(config)
    from qwen3_asr_tts_hf2api import create_app as _create_app

    app = _create_app()
    return await aiohttp_client(app)


class TestTTS:
    @pytest.mark.asyncio
    async def test_tts_success(self, client):
        with patch("qwen3_asr_tts_hf2api.tts.gradio_sse.call_gradio_sse", new_callable=AsyncMock) as mock_call, \
             patch("qwen3_asr_tts_hf2api.tts.gradio_sse.download_file", new_callable=AsyncMock) as mock_download:
            mock_call.return_value = [{"path": "/tmp/gradio/out.wav"}]
            mock_download.return_value = b"RIFF....WAVE"

            resp = await client.post(
                "/v1/audio/speech",
                json={"model": "qwen-tts", "input": "Hello world", "voice": "vivian"},
            )
            assert resp.status == 200
            assert resp.headers["Content-Type"] == "audio/wav"
            assert resp.headers.get("X-Warning") is None
            body = await resp.read()
            assert body == b"RIFF....WAVE"

    @pytest.mark.asyncio
    async def test_tts_unknown_voice(self, client):
        with patch("qwen3_asr_tts_hf2api.tts.gradio_sse.call_gradio_sse", new_callable=AsyncMock) as mock_call, \
             patch("qwen3_asr_tts_hf2api.tts.gradio_sse.download_file", new_callable=AsyncMock) as mock_download:
            mock_call.return_value = [{"path": "/tmp/gradio/out.wav"}]
            mock_download.return_value = b"RIFF....WAVE"

            resp = await client.post(
                "/v1/audio/speech",
                json={"model": "qwen-tts", "input": "Hello", "voice": "unknown"},
            )
            assert resp.status == 200
            assert resp.headers["Content-Type"] == "audio/wav"

    @pytest.mark.asyncio
    async def test_tts_missing_input(self, client):
        resp = await client.post(
            "/v1/audio/speech",
            json={"model": "qwen-tts"},
        )
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_tts_speed_warning(self, client):
        with patch("qwen3_asr_tts_hf2api.tts.gradio_sse.call_gradio_sse", new_callable=AsyncMock) as mock_call, \
             patch("qwen3_asr_tts_hf2api.tts.gradio_sse.download_file", new_callable=AsyncMock) as mock_download:
            mock_call.return_value = [{"path": "/tmp/gradio/out.wav"}]
            mock_download.return_value = b"RIFF....WAVE"

            resp = await client.post(
                "/v1/audio/speech",
                json={"model": "qwen-tts", "input": "Hello", "speed": 1.5},
            )
            assert resp.status == 200
            assert "speed-not-supported" in resp.headers.get("X-Warning", "")

    @pytest.mark.asyncio
    async def test_tts_format_warning(self, client):
        with patch("qwen3_asr_tts_hf2api.tts.gradio_sse.call_gradio_sse", new_callable=AsyncMock) as mock_call, \
             patch("qwen3_asr_tts_hf2api.tts.gradio_sse.download_file", new_callable=AsyncMock) as mock_download:
            mock_call.return_value = [{"path": "/tmp/gradio/out.wav"}]
            mock_download.return_value = b"RIFF....WAVE"

            resp = await client.post(
                "/v1/audio/speech",
                json={"model": "qwen-tts", "input": "Hello", "response_format": "mp3"},
            )
            assert resp.status == 200
            assert "format-conversion-not-supported" in resp.headers.get("X-Warning", "")

    @pytest.mark.asyncio
    async def test_cors_options(self, client):
        resp = await client.options("/v1/audio/speech")
        assert resp.status == 204
        assert resp.headers["Access-Control-Allow-Origin"] == "*"

    @pytest.mark.asyncio
    async def test_no_auth_pass(self, client):
        with patch("qwen3_asr_tts_hf2api.tts.gradio_sse.call_gradio_sse", new_callable=AsyncMock) as mock_call, \
             patch("qwen3_asr_tts_hf2api.tts.gradio_sse.download_file", new_callable=AsyncMock) as mock_download:
            mock_call.return_value = [{"path": "/tmp/gradio/out.wav"}]
            mock_download.return_value = b"RIFF....WAVE"

            resp = await client.post(
                "/v1/audio/speech",
                json={"model": "qwen-tts", "input": "Hello"},
            )
            assert resp.status == 200


class TestAuth:
    @pytest.mark.asyncio
    async def test_wrong_key(self, client_with_auth):
        resp = await client_with_auth.post(
            "/v1/audio/speech",
            json={"model": "qwen-tts", "input": "Hello"},
            headers={"Authorization": "Bearer wrong-key"},
        )
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_bearer_key(self, client_with_auth):
        with patch("qwen3_asr_tts_hf2api.tts.gradio_sse.call_gradio_sse", new_callable=AsyncMock) as mock_call, \
             patch("qwen3_asr_tts_hf2api.tts.gradio_sse.download_file", new_callable=AsyncMock) as mock_download:
            mock_call.return_value = [{"path": "/tmp/gradio/out.wav"}]
            mock_download.return_value = b"RIFF....WAVE"

            resp = await client_with_auth.post(
                "/v1/audio/speech",
                json={"model": "qwen-tts", "input": "Hello"},
                headers={"Authorization": "Bearer secret-key"},
            )
            assert resp.status == 200

    @pytest.mark.asyncio
    async def test_raw_key(self, client_with_auth):
        with patch("qwen3_asr_tts_hf2api.tts.gradio_sse.call_gradio_sse", new_callable=AsyncMock) as mock_call, \
             patch("qwen3_asr_tts_hf2api.tts.gradio_sse.download_file", new_callable=AsyncMock) as mock_download:
            mock_call.return_value = [{"path": "/tmp/gradio/out.wav"}]
            mock_download.return_value = b"RIFF....WAVE"

            resp = await client_with_auth.post(
                "/v1/audio/speech",
                json={"model": "qwen-tts", "input": "Hello"},
                headers={"Authorization": "secret-key"},
            )
            assert resp.status == 200
