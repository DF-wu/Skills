import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vits_tts_hf2api.ws_client import (
    GradioTimeoutError,
    GradioWSError,
    call_gradio_ws,
    download_result,
    upload_file,
)


@pytest.mark.asyncio
async def test_call_gradio_ws_success():
    mock_ws = AsyncMock()
    mock_ws.recv.side_effect = [
        json.dumps({"msg": "send_hash"}),
        json.dumps({"msg": "estimation", "rank": 0}),
        json.dumps({"msg": "send_data"}),
        json.dumps(
            {
                "msg": "process_completed",
                "success": True,
                "output": {"data": [{"path": "/tmp/test.wav"}]},
            }
        ),
    ]

    with patch(
        "vits_tts_hf2api.ws_client.websockets.connect",
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_ws),
            __aexit__=AsyncMock(return_value=False),
        ),
    ):
        result = await call_gradio_ws("https://example.com", 0, ["hello"], timeout=10)
        assert result == [{"path": "/tmp/test.wav"}]


@pytest.mark.asyncio
async def test_call_gradio_ws_error():
    mock_ws = AsyncMock()
    mock_ws.recv.side_effect = [
        json.dumps({"msg": "send_hash"}),
        json.dumps({"msg": "send_data"}),
        json.dumps(
            {
                "msg": "process_completed",
                "success": False,
                "output": {"error": "backend error"},
            }
        ),
    ]

    with patch(
        "vits_tts_hf2api.ws_client.websockets.connect",
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_ws),
            __aexit__=AsyncMock(return_value=False),
        ),
    ):
        with pytest.raises(GradioWSError, match="backend error"):
            await call_gradio_ws("https://example.com", 0, ["hello"], timeout=10)


@pytest.mark.asyncio
async def test_call_gradio_ws_timeout():
    mock_ws = AsyncMock()
    import asyncio

    mock_ws.recv.side_effect = asyncio.TimeoutError

    with patch(
        "vits_tts_hf2api.ws_client.websockets.connect",
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_ws),
            __aexit__=AsyncMock(return_value=False),
        ),
    ):
        with pytest.raises(GradioTimeoutError):
            await call_gradio_ws("https://example.com", 0, ["hello"], timeout=0.1)


@pytest.mark.asyncio
async def test_download_result_success():
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.read.return_value = b"wavdata"

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_ctx)

    data = await download_result(mock_session, "https://example.com", "/tmp/test.wav")
    assert data == b"wavdata"


@pytest.mark.asyncio
async def test_download_result_failure():
    mock_response = AsyncMock()
    mock_response.status = 404
    mock_response.text.return_value = "not found"

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_ctx)

    with pytest.raises(GradioWSError, match="Download failed 404"):
        await download_result(mock_session, "https://example.com", "/tmp/test.wav")


@pytest.mark.asyncio
async def test_upload_file_success():
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = ["/uploaded/file.wav"]

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_ctx)

    path = await upload_file(mock_session, "https://example.com", b"data", "file.wav")
    assert path == "/uploaded/file.wav"


@pytest.mark.asyncio
async def test_upload_file_failure():
    mock_response = AsyncMock()
    mock_response.status = 500
    mock_response.text.return_value = "server error"

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_ctx)

    with pytest.raises(GradioWSError, match="Upload failed 500"):
        await upload_file(mock_session, "https://example.com", b"data", "file.wav")
