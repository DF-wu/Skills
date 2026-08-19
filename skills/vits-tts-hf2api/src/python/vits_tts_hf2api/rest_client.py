import asyncio
import random
import string

import aiohttp

from . import config


def _generate_session_hash(length: int = 11) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


class GradioRESTError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class GradioTimeoutError(GradioRESTError):
    pass


async def call_gradio_rest(
    session: aiohttp.ClientSession,
    base_url: str,
    data: list,
    timeout: float = 120,
    fn_index: int | None = None,
    session_hash: str | None = None,
) -> bytes:
    url = f"{base_url}/api/generate/"
    payload: dict = {"data": data}
    if fn_index is not None:
        payload["fn_index"] = fn_index
    if session_hash is not None:
        payload["session_hash"] = session_hash

    try:
        async with session.post(
            url, json=payload, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise GradioRESTError(
                    f"Gradio REST API returned {resp.status}: {text}",
                    status_code=resp.status,
                )
            result = await resp.json()
    except asyncio.TimeoutError:
        raise GradioTimeoutError(f"Gradio REST API timed out after {timeout}s")
    except aiohttp.ClientError as e:
        raise GradioRESTError(f"Request failed: {e}")

    if "error" in result:
        raise GradioRESTError(result["error"])

    response_data = result.get("data")
    if not response_data or len(response_data) < 2:
        raise GradioRESTError("Unexpected response format from Gradio REST API")

    file_info = response_data[1]
    if isinstance(file_info, dict):
        file_path = file_info.get("name", "") or file_info.get("path", "")
    elif isinstance(file_info, str):
        file_path = file_info
    else:
        raise GradioRESTError(f"Unexpected file path type: {type(file_info)}")
    if not file_path:
        raise GradioRESTError("No file path in response")

    download_url = f"{base_url}/file={file_path}"
    try:
        async with session.get(
            download_url, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as download_resp:
            if download_resp.status != 200:
                text = await download_resp.text()
                raise GradioRESTError(
                    f"Download failed {download_resp.status}: {text}",
                    status_code=download_resp.status,
                )
            return await download_resp.read()
    except asyncio.TimeoutError:
        raise GradioTimeoutError(f"Download timed out after {timeout}s")
    except aiohttp.ClientError as e:
        raise GradioRESTError(f"Download failed: {e}")
