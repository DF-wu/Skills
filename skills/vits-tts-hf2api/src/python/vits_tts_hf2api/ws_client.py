import asyncio
import random
import string

import json

import aiohttp
import websockets

from . import config


class GradioWSError(RuntimeError):
    pass


class GradioTimeoutError(GradioWSError):
    pass


def _generate_session_hash(length: int = 11) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


async def call_gradio_ws(
    base_url: str, fn_index: int, data: list, timeout: float = 120
) -> list:
    """Call Gradio 3.x endpoint via WebSocket. Returns output data array."""
    session_hash = _generate_session_hash()
    ws_url = (
        base_url.replace("https://", "wss://").replace("http://", "ws://")
        + "/queue/join"
    )

    try:
        async with websockets.connect(
            ws_url, additional_headers={"User-Agent": config.USER_AGENT}
        ) as ws:
            # Step 2: Wait for send_hash
            msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
            if isinstance(msg, str):
                msg_data = json.loads(msg)
            else:
                msg_data = json.loads(msg.decode("utf-8"))
            if msg_data.get("msg") != "send_hash":
                raise GradioWSError(f"Expected send_hash, got: {msg_data}")

            # Step 3: Send hash
            await ws.send(
                json.dumps({"session_hash": session_hash, "fn_index": fn_index})
            )

            # Step 4+5: Wait for send_data (ignore estimation)
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
                msg_data = (
                    json.loads(msg)
                    if isinstance(msg, str)
                    else json.loads(msg.decode("utf-8"))
                )
                msg_type = msg_data.get("msg")
                if msg_type == "estimation":
                    continue
                if msg_type == "send_data":
                    break
                if msg_type == "process_completed":
                    # Early completion (error or empty)
                    if not msg_data.get("success", True):
                        error = msg_data.get("output", {}).get(
                            "error", "Unknown Gradio error"
                        )
                        raise GradioWSError(error)
                    return msg_data.get("output", {}).get("data", [])
                # Unexpected message, but keep waiting
                if msg_type not in ("estimation", "send_data"):
                    raise GradioWSError(f"Unexpected WS message: {msg_data}")

            # Step 6: Send data
            await ws.send(
                json.dumps(
                    {"session_hash": session_hash, "fn_index": fn_index, "data": data}
                )
            )

            # Step 7+8: Wait for process_completed
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
                msg_data = (
                    json.loads(msg)
                    if isinstance(msg, str)
                    else json.loads(msg.decode("utf-8"))
                )
                msg_type = msg_data.get("msg")
                if msg_type == "estimation":
                    continue
                if msg_type == "process_completed":
                    if not msg_data.get("success", True):
                        error = msg_data.get("output", {}).get(
                            "error", "Unknown Gradio error"
                        )
                        raise GradioWSError(error)
                    return msg_data.get("output", {}).get("data", [])
                if msg_type == "process_starts":
                    continue
                if msg_type == "progress":
                    continue
    except asyncio.TimeoutError:
        raise GradioTimeoutError(f"Gradio WebSocket timed out after {timeout}s")
    except websockets.exceptions.WebSocketException as e:
        raise GradioWSError(f"WebSocket error: {e}")


async def download_result(
    session: aiohttp.ClientSession, base_url: str, path: str
) -> bytes:
    """Download file by server path."""
    url = f"{base_url}/file={path}"
    async with session.get(url) as resp:
        if resp.status != 200:
            text = await resp.text()
            raise GradioWSError(f"Download failed {resp.status}: {text}")
        return await resp.read()


async def upload_file(
    session: aiohttp.ClientSession, base_url: str, file_bytes: bytes, filename: str
) -> str:
    """Upload file to Gradio 3.x, return server path."""
    url = f"{base_url}/upload"
    data = aiohttp.FormData()
    data.add_field(
        "files", file_bytes, filename=filename, content_type="application/octet-stream"
    )
    async with session.post(url, data=data) as resp:
        if resp.status != 200:
            text = await resp.text()
            raise GradioWSError(f"Upload failed {resp.status}: {text}")
        result = await resp.json()
        if isinstance(result, list) and result:
            return result[0]
        raise GradioWSError(f"Unexpected upload response: {result}")
