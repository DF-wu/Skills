import asyncio
import random
import string

import aiohttp

from . import config, rest_client


def is_retriable_rest_error(exc: rest_client.GradioRESTError) -> bool:
    if isinstance(exc, rest_client.GradioTimeoutError):
        return True
    if exc.status_code is not None:
        if 500 <= exc.status_code < 600:
            return True
        if exc.status_code == 429:
            return True
        if 400 <= exc.status_code < 500:
            return False
    msg = str(exc).lower()
    if any(kw in msg for kw in ("timed out", "connection", "refused", "reset")):
        return True
    if any(kw in msg for kw in ("unexpected response format", "unexpected file path")):
        return False
    if "request failed" in msg:
        inner = msg.split("request failed:")[-1].strip().lower()
        if any(kw in inner for kw in ("connect", "refused", "reset", "dns")):
            return True
        return False
    return False


# URLs that require session_hash (newer Gradio 3.50+ API)
_SESSION_HASH_URLS = set(config.BACKUP_REST_URLS)


def _needs_session_hash(url: str) -> bool:
    return url in _SESSION_HASH_URLS


def _make_session_hash() -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=11))


async def call_gradio_rest_with_retry(
    session: aiohttp.ClientSession,
    data: list,
    timeout: float | None = None,
    fn_index: int | None = 0,
) -> bytes:
    """Walk PRIMARY → BACKUP_REST_URLS in order.

    fn_index defaults to 0 because that is the only working function on every
    upstream Space (`/api/generate`). ikechan8370 tolerates a missing fn_index,
    but AHJoong / OldSecond return HTTP 422 without it — passing 0 explicitly
    keeps the call shape consistent with the documented bash and curl examples.
    """
    timeout = timeout or config.REQUEST_TIMEOUT
    urls = [config.BASE_URL] + config.BACKUP_REST_URLS
    if not urls:
        raise rest_client.GradioRESTError("No REST URLs configured")
    max_attempts = min(config.MAX_RETRIES, len(urls))
    last_exc = None
    for i in range(max_attempts):
        url = urls[i]
        sh = _make_session_hash() if _needs_session_hash(url) else None
        try:
            return await rest_client.call_gradio_rest(
                session,
                url,
                data,
                timeout=timeout,
                fn_index=fn_index,
                session_hash=sh,
            )
        except rest_client.GradioRESTError as e:
            last_exc = e
            if not is_retriable_rest_error(e):
                raise
            if i < max_attempts - 1:
                await asyncio.sleep(config.RETRY_DELAY)
    if last_exc is not None:
        raise last_exc
    raise rest_client.GradioRESTError("All REST attempts failed")
