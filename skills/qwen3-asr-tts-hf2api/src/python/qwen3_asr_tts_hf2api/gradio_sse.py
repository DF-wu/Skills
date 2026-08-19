import asyncio
import json
from typing import Any

import aiohttp


class GradioError(RuntimeError):
    pass


class GradioTimeoutError(GradioError):
    pass


class GradioApiError(GradioError):
    def __init__(self, message: str, event_id: str | None = None):
        super().__init__(message)
        self.event_id = event_id


async def call_gradio_sse(
    session: aiohttp.ClientSession,
    base_url: str,
    api_name: str,
    data: list[Any],
    timeout: float = 300,
) -> list[Any]:
    init_url = f"{base_url}/gradio_api/call{api_name}"
    try:
        async with session.post(
            init_url, json={"data": data}, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise GradioApiError(f"HTTP {resp.status}: {text}")
            init_json = await resp.json()
            event_id = init_json.get("event_id")
            if not event_id:
                raise GradioApiError(f"Missing event_id in response: {init_json}")
    except asyncio.TimeoutError:
        raise GradioTimeoutError(f"SSE stream timed out after {timeout}s") from None

    sse_url = f"{base_url}/gradio_api/call{api_name}/{event_id}"

    try:
        async with session.get(
            sse_url, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as sse_resp:
            if sse_resp.status >= 400:
                text = await sse_resp.text()
                raise GradioApiError(
                    f"HTTP {sse_resp.status}: {text}", event_id=event_id
                )

            result_data = None
            error_message = None

            async for line_bytes in sse_resp.content:
                line = line_bytes.decode("utf-8").strip()
                if line.startswith("event: "):
                    event_type = line[len("event: ") :]
                    data_line_bytes = await sse_resp.content.readline()
                    data_line = data_line_bytes.decode("utf-8").strip()
                    if data_line.startswith("data: "):
                        payload = data_line[len("data: ") :]
                    else:
                        payload = data_line

                    if event_type == "complete":
                        try:
                            result_data = json.loads(payload)
                        except Exception:
                            result_data = [payload]
                        break
                    elif event_type == "error":
                        error_message = payload
                        break
                    elif event_type == "generating":
                        continue
            else:
                if error_message is None and result_data is None:
                    raise GradioApiError(
                        "SSE stream ended without complete or error event",
                        event_id=event_id,
                    )

            if error_message is not None:
                raise GradioApiError(error_message, event_id=event_id)

            if result_data is None:
                raise GradioApiError(
                    "No result received from SSE stream", event_id=event_id
                )

            return result_data
    except asyncio.TimeoutError:
        raise GradioTimeoutError(f"SSE stream timed out after {timeout}s") from None


async def upload_file(
    session: aiohttp.ClientSession,
    base_url: str,
    file_bytes: bytes,
    filename: str,
    content_type: str = "application/octet-stream",
) -> str:
    upload_url = f"{base_url}/gradio_api/upload"
    data = aiohttp.FormData()
    data.add_field("files", file_bytes, filename=filename, content_type=content_type)

    async with session.post(upload_url, data=data) as resp:
        if resp.status >= 400:
            text = await resp.text()
            raise GradioApiError(f"HTTP {resp.status}: {text}")
        result = await resp.json()
        if isinstance(result, list) and len(result) > 0:
            return result[0]
        raise GradioApiError(f"Unexpected upload response: {result}")


async def download_file(
    session: aiohttp.ClientSession,
    base_url: str,
    path: str,
) -> bytes:
    download_url = f"{base_url}/gradio_api/file={path}"
    async with session.get(download_url) as resp:
        if resp.status >= 400:
            text = await resp.text()
            raise GradioApiError(f"HTTP {resp.status}: {text}")
        return await resp.read()
