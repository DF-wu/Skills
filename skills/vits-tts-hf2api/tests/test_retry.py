from unittest.mock import AsyncMock, patch

import pytest

from vits_tts_hf2api import config, rest_client, retry


class TestIsRetriable:
    def test_timeout_is_retriable(self):
        exc = rest_client.GradioTimeoutError("timed out")
        assert retry.is_retriable_rest_error(exc) is True

    def test_http_5xx_is_retriable(self):
        exc = rest_client.GradioRESTError("Server error", status_code=503)
        assert retry.is_retriable_rest_error(exc) is True

    def test_http_429_is_retriable(self):
        exc = rest_client.GradioRESTError("Rate limit", status_code=429)
        assert retry.is_retriable_rest_error(exc) is True

    def test_http_4xx_not_retriable(self):
        exc = rest_client.GradioRESTError("Bad request", status_code=400)
        assert retry.is_retriable_rest_error(exc) is False

    def test_http_404_not_retriable(self):
        exc = rest_client.GradioRESTError("Not found", status_code=404)
        assert retry.is_retriable_rest_error(exc) is False

    def test_unexpected_response_format_not_retriable(self):
        exc = rest_client.GradioRESTError("Unexpected response format")
        assert retry.is_retriable_rest_error(exc) is False

    def test_unexpected_file_path_not_retriable(self):
        exc = rest_client.GradioRESTError("Unexpected file path type")
        assert retry.is_retriable_rest_error(exc) is False

    def test_request_failed_connection_is_retriable(self):
        exc = rest_client.GradioRESTError("Request failed: Cannot connect to host")
        assert retry.is_retriable_rest_error(exc) is True

    def test_request_failed_refused_is_retriable(self):
        exc = rest_client.GradioRESTError("Request failed: Connection refused")
        assert retry.is_retriable_rest_error(exc) is True

    def test_request_failed_other_not_retriable(self):
        exc = rest_client.GradioRESTError("Request failed: unknown error")
        assert retry.is_retriable_rest_error(exc) is False

    def test_unknown_error_not_retriable_by_default(self):
        exc = rest_client.GradioRESTError("Some random Gradio queue error")
        assert retry.is_retriable_rest_error(exc) is False


class TestRetryChain:
    @pytest.fixture(autouse=True)
    def reset_config(self, monkeypatch):
        monkeypatch.setattr(config, "BASE_URL", "https://primary.example.com")
        monkeypatch.setattr(
            config,
            "BACKUP_REST_URLS",
            ["https://backup1.example.com", "https://backup2.example.com"],
        )
        monkeypatch.setattr(config, "REQUEST_TIMEOUT", 10)
        monkeypatch.setattr(config, "RETRY_DELAY", 0.0)

    async def test_success_on_primary(self):
        with patch.object(retry.rest_client, "call_gradio_rest") as m:
            m.return_value = b"audio"
            from vits_tts_hf2api import rest_client

            session = AsyncMock()
            result = await retry.call_gradio_rest_with_retry(
                session, ["text", "zh", 0, 0.6, 0.668, 1.2]
            )
            assert result == b"audio"
            assert m.call_count == 1
            assert m.call_args[0][1] == "https://primary.example.com"

    async def test_fall_back_to_backup1(self):
        from vits_tts_hf2api import rest_client

        with patch.object(retry.rest_client, "call_gradio_rest") as m:
            m.side_effect = [
                rest_client.GradioRESTError("Server error", status_code=503),
                b"backup-audio",
            ]
            session = AsyncMock()
            result = await retry.call_gradio_rest_with_retry(
                session, ["text", "zh", 0, 0.6, 0.668, 1.2]
            )
            assert result == b"backup-audio"
            assert m.call_count == 2
            assert m.call_args_list[1][0][1] == "https://backup1.example.com"

    async def test_exhaust_all_retries(self):
        from vits_tts_hf2api import rest_client

        with patch.object(retry.rest_client, "call_gradio_rest") as m:
            m.side_effect = rest_client.GradioRESTError("Server error", status_code=503)
            session = AsyncMock()
            with pytest.raises(rest_client.GradioRESTError):
                await retry.call_gradio_rest_with_retry(
                    session, ["text", "zh", 0, 0.6, 0.668, 1.2]
                )
            assert m.call_count == 3

    async def test_non_retriable_stops_immediately(self):
        from vits_tts_hf2api import rest_client

        with patch.object(retry.rest_client, "call_gradio_rest") as m:
            m.side_effect = rest_client.GradioRESTError("Bad request", status_code=400)
            session = AsyncMock()
            with pytest.raises(rest_client.GradioRESTError):
                await retry.call_gradio_rest_with_retry(
                    session, ["text", "zh", 0, 0.6, 0.668, 1.2]
                )
            assert m.call_count == 1

    async def test_passes_fn_index(self):
        from vits_tts_hf2api import rest_client

        with patch.object(retry.rest_client, "call_gradio_rest") as m:
            m.return_value = b"audio"
            session = AsyncMock()
            await retry.call_gradio_rest_with_retry(
                session, ["text", "zh", 0, 0.6, 0.668, 1.2], fn_index=15
            )
            assert m.call_args[1]["fn_index"] == 15
