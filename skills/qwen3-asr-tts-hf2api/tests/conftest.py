import pytest
from unittest.mock import AsyncMock, MagicMock


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
    mock_sess.post = AsyncMock(return_value=mock_resp)
    mock_sess.get = AsyncMock(return_value=mock_resp)
    mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
    mock_sess.__aexit__ = AsyncMock(return_value=None)
    return mock_sess


@pytest.fixture
async def client(aiohttp_client):
    from qwen3_asr_tts_hf2api import create_app

    app = create_app()
    return await aiohttp_client(app)
