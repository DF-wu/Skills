import base64
import json

from aiohttp import web

from . import config, rest_client, retry, speakers, ws_client


def _parse_params(body):
    text = body.get("input", "")
    if not text:
        return None, {"error": "input is required"}, 400
    text = text.replace("\n", " ").replace("\r", " ")

    truncated = False
    if len(text) > config.MAX_TEXT_LENGTH:
        text = text[: config.MAX_TEXT_LENGTH]
        truncated = True

    voice = body.get("voice") or body.get("speaker")

    language_key = body.get("language", config.DEFAULT_LANGUAGE)
    language = speakers.LANGUAGES.get(
        language_key, speakers.LANGUAGES.get(config.DEFAULT_LANGUAGE, "中文")
    )

    noise_scale = body.get("noise_scale", config.DEFAULT_NOISE_SCALE)
    try:
        noise_scale = float(noise_scale)
    except (TypeError, ValueError):
        noise_scale = config.DEFAULT_NOISE_SCALE
    noise_scale = max(0.1, min(1.0, noise_scale))

    noise_scale_w = body.get("noise_scale_w", config.DEFAULT_NOISE_SCALE_W)
    try:
        noise_scale_w = float(noise_scale_w)
    except (TypeError, ValueError):
        noise_scale_w = config.DEFAULT_NOISE_SCALE_W
    noise_scale_w = max(0.1, min(1.0, noise_scale_w))

    speed = body.get("speed")
    if speed is not None:
        try:
            speed_val = float(speed)
            if speed_val <= 0:
                speed_val = 1.0
            length_scale = 1.0 / speed_val
        except (TypeError, ValueError):
            length_scale = config.DEFAULT_LENGTH_SCALE
    else:
        length_scale = body.get("length_scale", config.DEFAULT_LENGTH_SCALE)
        try:
            length_scale = float(length_scale)
        except (TypeError, ValueError):
            length_scale = config.DEFAULT_LENGTH_SCALE
    length_scale = max(0.1, min(2.0, length_scale))

    return (
        {
            "text": text,
            "truncated": truncated,
            "voice": voice,
            "language": language,
            "noise_scale": noise_scale,
            "noise_scale_w": noise_scale_w,
            "length_scale": length_scale,
        },
        None,
        200,
    )


def _is_likely_empty_wav(audio_bytes: bytes) -> bool:
    """Detect the 556-byte 'silent WAV' upstream returns on degenerate input."""
    return (
        len(audio_bytes) >= 12
        and audio_bytes[:4] == b"RIFF"
        and audio_bytes[8:12] == b"WAVE"
        and len(audio_bytes) < 2048
    )


def _build_response(audio_bytes, truncated, body):
    headers = {"Content-Type": "audio/wav"}
    warnings = []
    if truncated:
        warnings.append("text-truncated")
    if _is_likely_empty_wav(audio_bytes):
        # Most common cause: language=mix without [ZH]/[JA] markers,
        # or a JP-only voice given Chinese text.
        warnings.append("empty-wav")
    response_format = body.get("response_format", "wav")
    if response_format and response_format != "wav":
        warnings.append("format-conversion-not-supported")
    if warnings:
        headers["X-Warning"] = ",".join(warnings)
    return web.Response(body=audio_bytes, headers=headers)


async def _handle_vits_models_speech(request, body, model_info, params):
    session = request.app["session"]
    try:
        audio_bytes = await rest_client.call_gradio_rest(
            session,
            config.VITS_MODELS_URL,
            [
                params["text"],
                model_info["language"],
                model_info["speaker_id"],
                params["noise_scale"],
                params["noise_scale_w"],
                params["length_scale"],
            ],
            timeout=config.REQUEST_TIMEOUT,
            fn_index=model_info["fn_index"],
        )
    except rest_client.GradioRESTError as e:
        return web.json_response({"error": str(e)}, status=502)
    return _build_response(audio_bytes, params["truncated"], body)


async def _ws_fallback(
    session,
    text,
    language,
    speaker_name,
    noise_scale,
    noise_scale_w,
    length_scale,
    truncated,
    body,
):
    fallback_text = text
    if len(fallback_text) > config.FALLBACK_MAX_TEXT_LENGTH:
        fallback_text = fallback_text[: config.FALLBACK_MAX_TEXT_LENGTH]
        truncated = True
    try:
        result = await ws_client.call_gradio_ws(
            config.FALLBACK_WS_URL,
            config.FN_INDEX,
            [
                fallback_text,
                language,
                speaker_name,
                noise_scale,
                noise_scale_w,
                length_scale,
            ],
            timeout=config.REQUEST_TIMEOUT,
        )
    except ws_client.GradioWSError as e:
        return web.json_response({"error": str(e)}, status=502)

    if not result:
        return web.json_response({"error": "Empty result from TTS backend"}, status=502)

    if (
        len(result) > 1
        and isinstance(result[1], str)
        and result[1].startswith("data:audio/wav;base64,")
    ):
        audio_bytes = base64.b64decode(result[1].split(",", 1)[1])
    else:
        file_info = result[0]
        if isinstance(file_info, dict):
            path = file_info.get("path")
        elif isinstance(file_info, str):
            path = file_info
        else:
            return web.json_response({"error": "Unexpected result format"}, status=502)
        if not path:
            return web.json_response({"error": "No file path in result"}, status=502)
        try:
            audio_bytes = await ws_client.download_result(
                session, config.FALLBACK_WS_URL, path
            )
        except ws_client.GradioWSError as e:
            return web.json_response({"error": str(e)}, status=502)

    return _build_response(audio_bytes, truncated, body)


async def handle_speech(request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    params, err_resp, err_status = _parse_params(body)
    if err_resp:
        return web.json_response(err_resp, status=err_status)

    voice = params["voice"]

    vits_model = speakers.resolve_vits_model_speaker(voice)
    if vits_model:
        return await _handle_vits_models_speech(request, body, vits_model, params)

    speaker_id = speakers.resolve_speaker(voice)
    speaker_name = speakers.resolve_speaker_gradio(voice)

    session = request.app["session"]

    data = [
        params["text"],
        params["language"],
        speaker_name,
        params["noise_scale"],
        params["noise_scale_w"],
        params["length_scale"],
    ]

    try:
        audio_bytes = await retry.call_gradio_rest_with_retry(
            session, data, timeout=config.REQUEST_TIMEOUT
        )
    except rest_client.GradioRESTError as e:
        if not retry.is_retriable_rest_error(e):
            return web.json_response({"error": str(e)}, status=502)
        return await _ws_fallback(
            session,
            params["text"],
            params["language"],
            speaker_name,
            params["noise_scale"],
            params["noise_scale_w"],
            params["length_scale"],
            params["truncated"],
            body,
        )

    return _build_response(audio_bytes, params["truncated"], body)
