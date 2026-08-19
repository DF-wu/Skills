from aiohttp import web

from . import config, gradio_sse, models


async def handle_speech(request: web.Request) -> web.StreamResponse:
    """POST /v1/audio/speech

    JSON body: {model, input, voice?, language?, response_format?, speed?}
    Returns: audio/wav binary stream
    """
    session = request.app["session"]

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    text = body.get("input") or body.get("text")
    if not text or not isinstance(text, str):
        return web.json_response(
            {"error": "Missing or invalid 'input' field"}, status=400
        )

    voice_id = body.get("voice", config.DEFAULT_VOICE)
    voice_name = models.resolve_voice(voice_id)

    lang_id = body.get("language", config.DEFAULT_LANGUAGE)
    lang_name = models.resolve_language(lang_id, target="tts")

    response_format = body.get("response_format", "wav")
    speed = body.get("speed")

    try:
        result = await gradio_sse.call_gradio_sse(
            session,
            config.TTS_BASE_URL,
            "/tts_interface",
            [text, voice_name, lang_name],
            timeout=config.REQUEST_TIMEOUT,
        )
    except gradio_sse.GradioError as exc:
        return web.json_response({"error": f"TTS upstream error: {exc}"}, status=502)

    if not result or not isinstance(result, list) or not isinstance(result[0], dict):
        return web.json_response(
            {"error": "Unexpected TTS response format"}, status=502
        )

    file_path = result[0].get("path")
    if not file_path:
        return web.json_response({"error": "No file path in TTS response"}, status=502)

    try:
        audio_bytes = await gradio_sse.download_file(
            session, config.TTS_BASE_URL, file_path
        )
    except gradio_sse.GradioError as exc:
        return web.json_response({"error": f"TTS download error: {exc}"}, status=502)

    response = web.StreamResponse(status=200)
    response.headers["Content-Type"] = "audio/wav"
    response.headers["Content-Length"] = str(len(audio_bytes))

    warnings = []
    if speed is not None:
        warnings.append("speed-not-supported")
    if response_format and response_format.lower() != "wav":
        warnings.append("format-conversion-not-supported")
    if warnings:
        response.headers["X-Warning"] = ", ".join(warnings)

    await response.prepare(request)
    await response.write(audio_bytes)
    await response.write_eof()
    return response
