import hashlib
import hmac
import logging
from typing import Any

import httpx2
from fastapi import HTTPException, status

from api.core.config import settings

logger = logging.getLogger(__name__)


class PaystackService:
    """Paystack payment gateway integration service."""

    def __init__(
        self,
        secret_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.secret_key = secret_key or settings.paystack.secret_key
        self.base_url = (base_url or settings.paystack.base_url).rstrip("/")

    async def initialize_transaction(
        self,
        email: str,
        amount_pesewas: int,
        reference: str,
        callback_url: str | None = None,
        metadata: dict[str, Any] | None = None,
        channels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Initializes a Paystack transaction and returns payment authorization details."""
        url = f"{self.base_url}/transaction/initialize"
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "email": email,
            "amount": amount_pesewas,
            "reference": reference,
            "currency": "GHS",
        }
        if callback_url:
            payload["callback_url"] = callback_url
        if metadata:
            payload["metadata"] = metadata
        if channels:
            payload["channels"] = channels

        try:
            async with httpx2.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                data = response.json()

                if response.status_code != 200 or not data.get("status"):
                    error_msg = data.get("message", "Paystack initialization failed")
                    logger.error(
                        f"Paystack API error: {error_msg} (status: {response.status_code})"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"Payment gateway error: {error_msg}",
                    )
                return data.get("data", {})
        except httpx2.RequestError as exc:
            logger.error(f"Network error communicating with Paystack: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to reach payment gateway. Please try again later.",
            ) from exc

    async def verify_transaction(self, reference: str) -> dict[str, Any]:
        """Verifies a transaction with Paystack by transaction reference."""
        url = f"{self.base_url}/transaction/verify/{reference}"
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
        }

        try:
            async with httpx2.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, headers=headers)
                data = response.json()

                if response.status_code != 200 or not data.get("status"):
                    error_msg = data.get("message", "Payment verification failed")
                    logger.error(f"Paystack verify error for {reference}: {error_msg}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Payment verification failed: {error_msg}",
                    )
                return data.get("data", {})
        except httpx2.RequestError as exc:
            logger.error(f"Network error verifying Paystack transaction: {exc}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Payment provider temporarily unavailable.",
            ) from exc

    @staticmethod
    def verify_webhook_signature(
        payload_bytes: bytes,
        signature_header: str | None,
        secret_key: str | None = None,
    ) -> bool:
        """Validates Paystack webhook HMAC SHA512 signature."""
        if not signature_header:
            return False

        key = (secret_key or settings.paystack.secret_key).encode("utf-8")
        computed_hash = hmac.new(key, payload_bytes, hashlib.sha512).hexdigest()
        return hmac.compare_digest(computed_hash, signature_header)


paystack_service = PaystackService()
