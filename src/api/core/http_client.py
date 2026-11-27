import asyncio
import logging
import random
from typing import Any

import httpx2

logger = logging.getLogger(__name__)

DEFAULT_RETRY_STATUS_CODES: tuple[int, ...] = (429, 500, 502, 503, 504)


class ResilientHttpClient:
    """Centralized outbound HTTP client with automatic exponential backoff, jitter,

    and transient error retry logic.
    """

    def __init__(
        self,
        timeout: float = 15.0,
        max_retries: int = 3,
        initial_backoff: float = 0.5,
        backoff_factor: float = 2.0,
        max_backoff: float = 5.0,
        retry_status_codes: tuple[int, ...] = DEFAULT_RETRY_STATUS_CODES,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max(1, max_retries)
        self.initial_backoff = initial_backoff
        self.backoff_factor = backoff_factor
        self.max_backoff = max_backoff
        self.retry_status_codes = retry_status_codes

    def _calculate_delay(
        self,
        attempt: int,
        retry_after_header: str | None = None,
    ) -> float:
        """Computes backoff delay, respecting Retry-After header and adding jitter."""
        if retry_after_header:
            try:
                header_delay = float(retry_after_header)
                return min(header_delay, self.max_backoff)
            except (ValueError, TypeError):
                pass

        # Exponential backoff: base * (factor ^ attempt) + random jitter
        base_delay = self.initial_backoff * (self.backoff_factor**attempt)
        delay = min(base_delay, self.max_backoff)
        jitter = random.uniform(0.0, 0.1 * delay) if delay > 0 else 0.0
        return delay + jitter

    async def request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx2.Response:
        """Dispatches an outbound HTTP request, automatically retrying transient network

        failures and 429/5xx status codes using exponential backoff.
        """
        request_timeout = kwargs.pop("timeout", self.timeout)
        last_exception: Exception | None = None
        last_response: httpx2.Response | None = None

        for attempt in range(self.max_retries):
            try:
                async with httpx2.AsyncClient(timeout=request_timeout) as client:
                    method_func = getattr(client, method.lower(), None)
                    if callable(method_func) and method.upper() in (
                        "GET",
                        "POST",
                        "PUT",
                        "DELETE",
                        "PATCH",
                        "HEAD",
                        "OPTIONS",
                    ):
                        response = await method_func(url, **kwargs)
                    else:
                        response = await client.request(method, url, **kwargs)

                # If status code indicates transient server error or rate limiting, retry
                if response.status_code in self.retry_status_codes:
                    last_response = response
                    if attempt < self.max_retries - 1:
                        retry_after = response.headers.get("retry-after")
                        delay = self._calculate_delay(attempt, retry_after)
                        logger.warning(
                            f"Transient HTTP {response.status_code} received from {method} {url} "
                            f"(attempt {attempt + 1}/{self.max_retries}). Retrying in {delay:.2f}s..."
                        )
                        await asyncio.sleep(delay)
                        continue

                return response

            except httpx2.RequestError as exc:
                last_exception = exc
                if attempt < self.max_retries - 1:
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        f"Network error on {method} {url}: {exc} "
                        f"(attempt {attempt + 1}/{self.max_retries}). Retrying in {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        f"Max retries ({self.max_retries}) exceeded for {method} {url}: {exc}"
                    )
                    raise

        if last_response is not None:
            return last_response

        if last_exception is not None:
            raise last_exception

        raise httpx2.RequestError(f"Request failed with no response for {method} {url}")

    async def get(self, url: str, **kwargs: Any) -> httpx2.Response:
        """Executes a GET request with retry resilience."""
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx2.Response:
        """Executes a POST request with retry resilience."""
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx2.Response:
        """Executes a PUT request with retry resilience."""
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx2.Response:
        """Executes a DELETE request with retry resilience."""
        return await self.request("DELETE", url, **kwargs)


http_client = ResilientHttpClient()
