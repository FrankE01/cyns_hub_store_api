from unittest.mock import AsyncMock, MagicMock, patch

import httpx2
import pytest

from api.core.http_client import ResilientHttpClient


@pytest.mark.asyncio
async def test_resilient_http_client_immediate_success() -> None:
    """Verify that a 200 OK request succeeds immediately without retry or sleep."""
    client = ResilientHttpClient(max_retries=3, initial_backoff=0.01)

    mock_resp = MagicMock(spec=httpx2.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok"}

    with (
        patch("httpx2.AsyncClient.request", new_callable=AsyncMock) as mock_request,
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_request.return_value = mock_resp

        response = await client.get("https://api.example.com/test")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert mock_request.call_count == 1
        mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_resilient_http_client_convenience_methods() -> None:
    """Verify get, post, put, delete methods map to corresponding HTTP verbs."""
    client = ResilientHttpClient(max_retries=1)

    mock_resp = MagicMock(spec=httpx2.Response)
    mock_resp.status_code = 200

    with (
        patch("httpx2.AsyncClient.get", new_callable=AsyncMock) as mock_get,
        patch("httpx2.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        patch("httpx2.AsyncClient.put", new_callable=AsyncMock) as mock_put,
        patch("httpx2.AsyncClient.delete", new_callable=AsyncMock) as mock_delete,
    ):
        mock_get.return_value = mock_resp
        mock_post.return_value = mock_resp
        mock_put.return_value = mock_resp
        mock_delete.return_value = mock_resp

        await client.get("https://api.example.com/item")
        mock_get.assert_called_once()

        await client.post("https://api.example.com/item", json={"key": "val"})
        mock_post.assert_called_once()

        await client.put("https://api.example.com/item", json={"key": "val"})
        mock_put.assert_called_once()

        await client.delete("https://api.example.com/item")
        mock_delete.assert_called_once()


@pytest.mark.asyncio
async def test_resilient_http_client_non_retryable_status_short_circuits() -> None:
    """Verify that client errors (e.g. 400, 401, 404) return immediately without retry."""
    client = ResilientHttpClient(max_retries=3, initial_backoff=0.01)

    mock_resp_400 = MagicMock(spec=httpx2.Response)
    mock_resp_400.status_code = 400
    mock_resp_400.json.return_value = {"error": "Bad Request"}

    with (
        patch("httpx2.AsyncClient.request", new_callable=AsyncMock) as mock_request,
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_request.return_value = mock_resp_400

        response = await client.post("https://api.example.com/fail", json={})

        assert response.status_code == 400
        assert mock_request.call_count == 1
        mock_sleep.assert_not_called()


@pytest.mark.asyncio
async def test_resilient_http_client_retries_transient_status_codes() -> None:
    """Verify that 503 and 500 status codes trigger retries, then succeed on 200."""
    client = ResilientHttpClient(max_retries=3, initial_backoff=0.05, max_backoff=1.0)

    resp_503 = MagicMock(spec=httpx2.Response)
    resp_503.status_code = 503
    resp_503.headers = {}

    resp_500 = MagicMock(spec=httpx2.Response)
    resp_500.status_code = 500
    resp_500.headers = {}

    resp_200 = MagicMock(spec=httpx2.Response)
    resp_200.status_code = 200
    resp_200.headers = {}

    with (
        patch("httpx2.AsyncClient.request", new_callable=AsyncMock) as mock_request,
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_request.side_effect = [resp_503, resp_500, resp_200]

        response = await client.request("GET", "https://api.example.com/retry-test")

        assert response.status_code == 200
        assert mock_request.call_count == 3
        assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_resilient_http_client_transient_status_exhaustion() -> None:
    """Verify that exhausting retries on 503 returns the final 503 response."""
    client = ResilientHttpClient(max_retries=3, initial_backoff=0.01)

    resp_503 = MagicMock(spec=httpx2.Response)
    resp_503.status_code = 503
    resp_503.headers = {}

    with (
        patch("httpx2.AsyncClient.request", new_callable=AsyncMock) as mock_request,
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_request.return_value = resp_503

        response = await client.request("GET", "https://api.example.com/always-503")

        assert response.status_code == 503
        assert mock_request.call_count == 3
        assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_resilient_http_client_retries_network_exceptions() -> None:
    """Verify that httpx2.RequestError triggers retries and succeeds if subsequent attempt works."""
    client = ResilientHttpClient(max_retries=3, initial_backoff=0.01)

    resp_200 = MagicMock(spec=httpx2.Response)
    resp_200.status_code = 200

    with (
        patch("httpx2.AsyncClient.request", new_callable=AsyncMock) as mock_request,
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_request.side_effect = [
            httpx2.ConnectError("Connection refused"),
            resp_200,
        ]

        response = await client.request("GET", "https://api.example.com/network-test")

        assert response.status_code == 200
        assert mock_request.call_count == 2
        assert mock_sleep.call_count == 1


@pytest.mark.asyncio
async def test_resilient_http_client_network_exception_exhaustion() -> None:
    """Verify that exhausting retries on network exception raises httpx2.RequestError."""
    client = ResilientHttpClient(max_retries=2, initial_backoff=0.01)

    with (
        patch("httpx2.AsyncClient.request", new_callable=AsyncMock) as mock_request,
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_request.side_effect = httpx2.ConnectTimeout("Connection timed out")

        with pytest.raises(httpx2.ConnectTimeout):
            await client.request("GET", "https://api.example.com/timeout")

        assert mock_request.call_count == 2
        assert mock_sleep.call_count == 1


def test_calculate_delay_with_retry_after() -> None:
    """Verify that _calculate_delay parses Retry-After header and caps to max_backoff."""
    client = ResilientHttpClient(
        initial_backoff=1.0, backoff_factor=2.0, max_backoff=10.0
    )

    # Valid header delay
    delay = client._calculate_delay(attempt=0, retry_after_header="3.5")
    assert delay == 3.5

    # Capped at max_backoff
    delay_capped = client._calculate_delay(attempt=0, retry_after_header="60.0")
    assert delay_capped == 10.0

    # Malformed header falls back to exponential backoff
    delay_fallback = client._calculate_delay(
        attempt=0, retry_after_header="invalid_sec"
    )
    # Base delay is 1.0, jitter between 0 and 0.1
    assert 1.0 <= delay_fallback <= 1.15


def test_calculate_delay_exponential_growth() -> None:
    """Verify that subsequent attempts increase delay with backoff factor."""
    client = ResilientHttpClient(
        initial_backoff=1.0, backoff_factor=2.0, max_backoff=30.0
    )

    delay_0 = client._calculate_delay(attempt=0)
    delay_1 = client._calculate_delay(attempt=1)
    delay_2 = client._calculate_delay(attempt=2)

    # Attempt 0: base 1.0
    assert 1.0 <= delay_0 <= 1.1
    # Attempt 1: base 2.0
    assert 2.0 <= delay_1 <= 2.2
    # Attempt 2: base 4.0
    assert 4.0 <= delay_2 <= 4.4
