import pytest
from aiohttp import web

from vits_tts_hf2api import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def cli(aiohttp_client, app):
    return await aiohttp_client(app)
