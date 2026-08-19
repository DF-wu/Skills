from aiohttp import web

from . import config, gradio_sse, models


async def handle_transcriptions(request: web.Request) -> web.Response:
    """POST /v1/audio/transcriptions

    multipart: file, model?, language?
    Returns: JSON {text, language?}
    """
    session = request.app["session"]

    try:
        reader = await request.multipart()
    except Exception:
        return web.json_response({"error": "Invalid multipart body"}, status=400)

    file_bytes: bytes | None = None
    filename: str = "audio.wav"
    model_name: str = "qwen3-asr"
    language_id: str = config.DEFAULT_LANGUAGE

    field: web.BodyPartReader | None = None
    try:
        while True:
            field = await reader.next()  # type: ignore[assignment]
            if field is None:
                break
            field_name = field.name
            if field_name == "file":
                file_bytes = await field.read(decode=False)
                filename = field.filename or filename
            elif field_name == "model":
                model_name = (await field.text()) or model_name
            elif field_name == "language":
                language_id = (await field.text()) or language_id
    except Exception:
        return web.json_response(
            {"error": "Error reading multipart fields"}, status=400
        )

    if file_bytes is None:
        return web.json_response({"error": "Missing 'file' field"}, status=400)

    lang_name = models.resolve_language(language_id, target="asr")

    try:
        server_path = await gradio_sse.upload_file(
            session,
            config.ASR_BASE_URL,
            file_bytes,
            filename,
        )
    except gradio_sse.GradioError as exc:
        return web.json_response({"error": f"ASR upload error: {exc}"}, status=502)

    return_ts = model_name.endswith("itn")
    payload = [
        {"path": server_path, "meta": {"_type": "gradio.FileData"}},
        lang_name,
        return_ts,
    ]

    try:
        result = await gradio_sse.call_gradio_sse(
            session,
            config.ASR_BASE_URL,
            "/transcribe",
            payload,
            timeout=config.REQUEST_TIMEOUT,
        )
    except gradio_sse.GradioApiError as exc:
        if str(exc) == "null":
            return web.json_response(
                {"error": "ASR upstream unavailable: Space returns error:null"},
                status=503,
            )
        return web.json_response({"error": f"ASR upstream error: {exc}"}, status=502)
    except gradio_sse.GradioError as exc:
        return web.json_response({"error": f"ASR upstream error: {exc}"}, status=502)

    if not result or not isinstance(result, list):
        return web.json_response(
            {"error": "Unexpected ASR response format"}, status=502
        )

    # HF Space transcribe returns: [language, text, timestamps_json, html]
    detected_lang = result[0] if len(result) > 0 else ""
    transcription_text = result[1] if len(result) > 1 else ""

    response = {"text": transcription_text}
    if detected_lang:
        response["language"] = detected_lang

    return web.json_response(response)
