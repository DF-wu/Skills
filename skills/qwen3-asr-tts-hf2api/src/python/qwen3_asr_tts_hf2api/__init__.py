import aiohttp
from aiohttp import web
from . import config, tts, asr, models


async def check_auth(request: web.Request) -> bool:
    if apikey := config.API_KEY:
        auth = request.headers.get("Authorization", "")
        if auth not in (apikey, f"Bearer {apikey}"):
            return False
    return True


@web.middleware
async def cors_auth_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        response = web.Response(status=204)
    else:
        if not await check_auth(request):
            response = web.json_response({"error": "Unauthorized"}, status=401)
        else:
            response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


async def health(request: web.Request):
    return web.json_response({"status": "ok"})


async def get_models(request: web.Request):
    return web.json_response(
        {
            "data": [
                {"id": "qwen-tts", "type": "tts"},
                {"id": "qwen3-asr", "type": "asr"},
                {"id": "qwen3-asr:itn", "type": "asr"},
            ],
            "voices": models.TTS_VOICES,
            "languages": models.TTS_LANGUAGES,
        }
    )


async def init_session(app: web.Application):
    app["session"] = aiohttp.ClientSession(
        headers={"User-Agent": config.USER_AGENT},
        timeout=aiohttp.ClientTimeout(total=config.REQUEST_TIMEOUT),
    )


async def on_cleanup(app: web.Application):
    await app["session"].close()


def create_app() -> web.Application:
    app = web.Application(middlewares=[cors_auth_middleware])
    app.on_startup.append(init_session)
    app.on_cleanup.append(on_cleanup)
    app.router.add_get("/health", health)
    app.router.add_get("/v1/models", get_models)
    app.router.add_post("/v1/audio/speech", tts.handle_speech)
    app.router.add_post("/v1/audio/transcriptions", asr.handle_transcriptions)
    return app


def main():
    web.run_app(create_app(), host=config.HOST, port=config.PORT)
