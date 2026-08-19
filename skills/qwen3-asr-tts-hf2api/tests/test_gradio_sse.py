import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from qwen3_asr_tts_hf2api import gradio_sse


class MockStream:
    def __init__(self, lines):
        self._lines = lines
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._lines):
            raise StopAsyncIteration
        line = self._lines[self._idx]
        self._idx += 1
        return line

    async def readline(self):
        if self._idx >= len(self._lines):
            return b""
        line = self._lines[self._idx]
        self._idx += 1
        return line


@pytest.fixture
def mock_session():
    mock_resp = MagicMock()
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={})
    mock_resp.text = AsyncMock(return_value="")
    mock_resp.read = AsyncMock(return_value=b"")

    mock_sess = MagicMock()
    mock_sess.post = MagicMock(return_value=mock_resp)
    mock_sess.get = MagicMock(return_value=mock_resp)
    mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
    mock_sess.__aexit__ = AsyncMock(return_value=None)
    return mock_sess


@pytest.mark.asyncio
async def test_call_gradio_sse_complete(mock_session):
    init_resp = MagicMock()
    init_resp.__aenter__ = AsyncMock(return_value=init_resp)
    init_resp.__aexit__ = AsyncMock(return_value=None)
    init_resp.status = 200
    init_resp.json = AsyncMock(return_value={"event_id": "evt-123"})

    sse_resp = MagicMock()
    sse_resp.__aenter__ = AsyncMock(return_value=sse_resp)
    sse_resp.__aexit__ = AsyncMock(return_value=None)
    sse_resp.status = 200
    sse_resp.content = MockStream(
        [
            b"event: generating\n",
            b"data: null\n",
            b"event: complete\n",
            b'data: [{"path": "/tmp/gradio/test.wav"}]\n',
        ]
    )

    mock_session.post = MagicMock(return_value=init_resp)
    mock_session.get = MagicMock(return_value=sse_resp)

    result = await gradio_sse.call_gradio_sse(
        mock_session, "https://space.hf.space", "/tts_interface", ["hello"]
    )
    assert result == [{"path": "/tmp/gradio/test.wav"}]


@pytest.mark.asyncio
async def test_call_gradio_sse_error_null(mock_session):
    init_resp = MagicMock()
    init_resp.__aenter__ = AsyncMock(return_value=init_resp)
    init_resp.__aexit__ = AsyncMock(return_value=None)
    init_resp.status = 200
    init_resp.json = AsyncMock(return_value={"event_id": "evt-456"})

    sse_resp = MagicMock()
    sse_resp.__aenter__ = AsyncMock(return_value=sse_resp)
    sse_resp.__aexit__ = AsyncMock(return_value=None)
    sse_resp.status = 200
    sse_resp.content = MockStream(
        [
            b"event: error\n",
            b"data: null\n",
        ]
    )

    mock_session.post = MagicMock(return_value=init_resp)
    mock_session.get = MagicMock(return_value=sse_resp)

    with pytest.raises(gradio_sse.GradioApiError) as exc_info:
        await gradio_sse.call_gradio_sse(
            mock_session, "https://space.hf.space", "/transcribe", [{}]
        )
    assert str(exc_info.value) == "null"
    assert exc_info.value.event_id == "evt-456"


@pytest.mark.asyncio
async def test_call_gradio_sse_error_message(mock_session):
    init_resp = MagicMock()
    init_resp.__aenter__ = AsyncMock(return_value=init_resp)
    init_resp.__aexit__ = AsyncMock(return_value=None)
    init_resp.status = 200
    init_resp.json = AsyncMock(return_value={"event_id": "evt-789"})

    sse_resp = MagicMock()
    sse_resp.__aenter__ = AsyncMock(return_value=sse_resp)
    sse_resp.__aexit__ = AsyncMock(return_value=None)
    sse_resp.status = 200
    sse_resp.content = MockStream(
        [
            b"event: error\n",
            b'data: "rate limited"\n',
            b"\n",
        ]
    )

    mock_session.post = MagicMock(return_value=init_resp)
    mock_session.get = MagicMock(return_value=sse_resp)

    with pytest.raises(gradio_sse.GradioApiError) as exc_info:
        await gradio_sse.call_gradio_sse(
            mock_session, "https://space.hf.space", "/api", ["test"]
        )
    assert "rate limited" in str(exc_info.value)
    assert exc_info.value.event_id == "evt-789"


@pytest.mark.asyncio
async def test_call_gradio_sse_timeout(mock_session):
    init_resp = MagicMock()
    init_resp.__aenter__ = AsyncMock(return_value=init_resp)
    init_resp.__aexit__ = AsyncMock(return_value=None)
    init_resp.status = 200
    init_resp.json = AsyncMock(return_value={"event_id": "evt-timeout"})

    get_resp = MagicMock()
    get_resp.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())
    get_resp.__aexit__ = AsyncMock(return_value=None)

    mock_session.post = MagicMock(return_value=init_resp)
    mock_session.get = MagicMock(return_value=get_resp)

    with pytest.raises(gradio_sse.GradioTimeoutError):
        await gradio_sse.call_gradio_sse(
            mock_session, "https://space.hf.space", "/api", [], timeout=1
        )


@pytest.mark.asyncio
async def test_upload_file(mock_session):
    upload_resp = MagicMock()
    upload_resp.__aenter__ = AsyncMock(return_value=upload_resp)
    upload_resp.__aexit__ = AsyncMock(return_value=None)
    upload_resp.status = 200
    upload_resp.json = AsyncMock(return_value=["/tmp/gradio/uploaded.wav"])

    mock_session.post = MagicMock(return_value=upload_resp)

    result = await gradio_sse.upload_file(
        mock_session,
        "https://space.hf.space",
        b"fake audio",
        "test.wav",
        content_type="audio/wav",
    )
    assert result == "/tmp/gradio/uploaded.wav"


@pytest.mark.asyncio
async def test_upload_file_http_error(mock_session):
    error_resp = MagicMock()
    error_resp.__aenter__ = AsyncMock(return_value=error_resp)
    error_resp.__aexit__ = AsyncMock(return_value=None)
    error_resp.status = 500
    error_resp.text = AsyncMock(return_value="Internal Server Error")

    mock_session.post = MagicMock(return_value=error_resp)

    with pytest.raises(gradio_sse.GradioApiError) as exc_info:
        await gradio_sse.upload_file(
            mock_session, "https://space.hf.space", b"x", "x.wav"
        )
    assert "500" in str(exc_info.value)


@pytest.mark.asyncio
async def test_download_file(mock_session):
    file_bytes = b"RIFF....WAVE"
    download_resp = MagicMock()
    download_resp.__aenter__ = AsyncMock(return_value=download_resp)
    download_resp.__aexit__ = AsyncMock(return_value=None)
    download_resp.status = 200
    download_resp.read = AsyncMock(return_value=file_bytes)

    mock_session.get = MagicMock(return_value=download_resp)

    result = await gradio_sse.download_file(
        mock_session, "https://space.hf.space", "/tmp/gradio/out.wav"
    )
    assert result == file_bytes


@pytest.mark.asyncio
async def test_download_file_http_error(mock_session):
    error_resp = MagicMock()
    error_resp.__aenter__ = AsyncMock(return_value=error_resp)
    error_resp.__aexit__ = AsyncMock(return_value=None)
    error_resp.status = 404
    error_resp.text = AsyncMock(return_value="Not Found")

    mock_session.get = MagicMock(return_value=error_resp)

    with pytest.raises(gradio_sse.GradioApiError) as exc_info:
        await gradio_sse.download_file(
            mock_session, "https://space.hf.space", "/tmp/gradio/out.wav"
        )
    assert "404" in str(exc_info.value)
