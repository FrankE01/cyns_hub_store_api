import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import settings
from api.core.http_client import ResilientHttpClient, http_client
from api.models.notification import (
    NotificationChannel,
    NotificationLog,
    NotificationStatus,
)
from api.models.order import Order

logger = logging.getLogger(__name__)


class NotificationService:
    """Service handling outbound SMS via Arkesel and WhatsApp alerts for customer orders."""

    def __init__(
        self,
        arkesel_api_key: str | None = None,
        arkesel_sender_id: str | None = None,
        arkesel_sms_url: str | None = None,
        client: ResilientHttpClient | None = None,
    ) -> None:
        self.arkesel_api_key = arkesel_api_key or settings.notifications.arkesel_api_key
        self.arkesel_sender_id = (
            arkesel_sender_id or settings.notifications.arkesel_sender_id
        )
        self.arkesel_sms_url = arkesel_sms_url or settings.notifications.arkesel_sms_url
        self.http_client = client or http_client

    @staticmethod
    def normalize_phone_ghana(phone: str) -> str:
        """Normalizes local/international Ghanaian phone numbers to 233XXXXXXXXX format."""
        cleaned = "".join(c for c in phone if c.isdigit())
        if cleaned.startswith("0") and len(cleaned) == 10:
            return f"233{cleaned[1:]}"
        if cleaned.startswith("233") and len(cleaned) == 12:
            return cleaned
        return cleaned

    async def send_arkesel_sms(
        self,
        recipient: str,
        message: str,
    ) -> dict[str, Any]:
        """Dispatches SMS through the Arkesel SMS API v2 gateway."""
        if not settings.notifications.enabled:
            logger.info("Outbound notifications are globally disabled. Skipping SMS.")
            return {"status": "skipped", "reason": "notifications_disabled"}

        normalized = self.normalize_phone_ghana(recipient)
        headers = {
            "api-key": self.arkesel_api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "sender": self.arkesel_sender_id,
            "message": message,
            "recipients": [normalized],
        }

        try:
            response = await self.http_client.post(
                self.arkesel_sms_url,
                headers=headers,
                json=payload,
                timeout=10.0,
            )
            data = response.json() if response.content else {}
            if response.status_code == 200:
                logger.info(f"Arkesel SMS dispatched successfully to {normalized}")
                return {"status": "sent", "provider_response": data}
            else:
                logger.error(f"Arkesel SMS failed ({response.status_code}): {data}")
                return {
                    "status": "failed",
                    "error": data.get("message", "Gateway error"),
                    "provider_response": data,
                }
        except Exception as exc:
            logger.error(f"Network error sending Arkesel SMS to {recipient}: {exc}")
            return {"status": "failed", "error": str(exc)}

    async def send_whatsapp(
        self,
        recipient: str,
        message: str,
    ) -> dict[str, Any]:
        """Dispatches WhatsApp alert via Meta Cloud / Arkesel WABA gateway."""
        if (
            not settings.notifications.enabled
            or not settings.notifications.whatsapp_enabled
        ):
            return {"status": "skipped", "reason": "whatsapp_disabled"}

        normalized = self.normalize_phone_ghana(recipient)
        url = f"{settings.notifications.whatsapp_api_url.rstrip('/')}/{settings.notifications.whatsapp_phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {settings.notifications.whatsapp_access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalized,
            "type": "text",
            "text": {"preview_url": False, "body": message},
        }

        try:
            response = await self.http_client.post(
                url,
                headers=headers,
                json=payload,
                timeout=10.0,
            )
            data = response.json() if response.content else {}
            if response.status_code in (200, 201):
                logger.info(f"WhatsApp alert dispatched successfully to {normalized}")
                return {"status": "sent", "provider_response": data}
            else:
                logger.error(
                    f"WhatsApp dispatch failed ({response.status_code}): {data}"
                )
                return {
                    "status": "failed",
                    "error": data.get("error", {}).get("message", "WhatsApp API error"),
                    "provider_response": data,
                }
        except Exception as exc:
            logger.error(f"Network error sending WhatsApp to {recipient}: {exc}")
            return {"status": "failed", "error": str(exc)}

    async def _dispatch_and_log(
        self,
        db: AsyncSession,
        order: Order | None,
        recipient: str,
        message: str,
    ) -> None:
        """Dispatches notification via SMS and optional WhatsApp, and logs audit record."""
        # 1. Send SMS via Arkesel
        sms_result = await self.send_arkesel_sms(recipient=recipient, message=message)
        sms_status = (
            NotificationStatus.SENT
            if sms_result.get("status") == "sent"
            else NotificationStatus.SKIPPED
            if sms_result.get("status") == "skipped"
            else NotificationStatus.FAILED
        )

        sms_log = NotificationLog(
            id=uuid.uuid4(),
            order_id=order.id if order else None,
            channel=NotificationChannel.SMS,
            recipient=recipient,
            message=message,
            status=sms_status,
            provider_response=sms_result.get("provider_response"),
            error_message=sms_result.get("error"),
            created_at=datetime.now(UTC),
        )
        db.add(sms_log)

        # 2. Send WhatsApp if enabled
        if settings.notifications.whatsapp_enabled:
            wa_result = await self.send_whatsapp(recipient=recipient, message=message)
            wa_status = (
                NotificationStatus.SENT
                if wa_result.get("status") == "sent"
                else NotificationStatus.SKIPPED
                if wa_result.get("status") == "skipped"
                else NotificationStatus.FAILED
            )
            wa_log = NotificationLog(
                id=uuid.uuid4(),
                order_id=order.id if order else None,
                channel=NotificationChannel.WHATSAPP,
                recipient=recipient,
                message=message,
                status=wa_status,
                provider_response=wa_result.get("provider_response"),
                error_message=wa_result.get("error"),
                created_at=datetime.now(UTC),
            )
            db.add(wa_log)

        try:
            await db.commit()
        except Exception as exc:
            logger.warning(f"Could not persist notification log: {exc}")
            await db.rollback()

    # -----------------------------------------------------------------------
    # Transactional Trigger Methods (Fail-safe)
    # -----------------------------------------------------------------------

    async def notify_order_created(
        self,
        db: AsyncSession,
        order: Order,
    ) -> None:
        """Dispatches customer confirmation when a new order is captured."""
        try:
            tracking_url = (
                f"{settings.notifications.storefront_url}/orders/{order.reference}"
            )
            message = (
                f"Hello {order.customer_name}! Your order {order.reference} (GHS {order.total:.2f}) "
                f"at Cyn's Hub has been placed. Track order: {tracking_url}"
            )
            await self._dispatch_and_log(
                db=db,
                order=order,
                recipient=order.customer_phone,
                message=message,
            )
        except Exception as exc:
            logger.error(f"Error in notify_order_created: {exc}")

    async def notify_payment_confirmed(
        self,
        db: AsyncSession,
        order: Order,
    ) -> None:
        """Dispatches payment confirmation alert when MoMo / Paystack payment is confirmed."""
        try:
            tracking_url = (
                f"{settings.notifications.storefront_url}/orders/{order.reference}"
            )
            status_desc = (
                "awaiting pre-order stock" if order.is_pre_order else "being processed"
            )
            message = (
                f"Hello {order.customer_name}! Payment of GHS {order.total:.2f} for order "
                f"{order.reference} is confirmed. Your order is {status_desc}! Track: {tracking_url}"
            )
            await self._dispatch_and_log(
                db=db,
                order=order,
                recipient=order.customer_phone,
                message=message,
            )
        except Exception as exc:
            logger.error(f"Error in notify_payment_confirmed: {exc}")

    async def notify_out_for_delivery(
        self,
        db: AsyncSession,
        order: Order,
    ) -> None:
        """Dispatches dispatch alert when courier takes possession of order."""
        try:
            message = (
                f"Hello {order.customer_name}! Your Cyn's Hub order {order.reference} is out for "
                f"delivery to {order.delivery_address}. Please keep your phone reachable!"
            )
            await self._dispatch_and_log(
                db=db,
                order=order,
                recipient=order.customer_phone,
                message=message,
            )
        except Exception as exc:
            logger.error(f"Error in notify_out_for_delivery: {exc}")

    async def notify_order_completed(
        self,
        db: AsyncSession,
        order: Order,
    ) -> None:
        """Dispatches thank-you delivery completion alert."""
        try:
            message = (
                f"Hello {order.customer_name}! Your order {order.reference} has been delivered. "
                "Thank you for shopping with Cyn's Hub! We hope you love your pieces."
            )
            await self._dispatch_and_log(
                db=db,
                order=order,
                recipient=order.customer_phone,
                message=message,
            )
        except Exception as exc:
            logger.error(f"Error in notify_order_completed: {exc}")

    async def notify_order_cancelled(
        self,
        db: AsyncSession,
        order: Order,
    ) -> None:
        """Dispatches cancellation notice to customer."""
        try:
            message = (
                f"Hello {order.customer_name}, order {order.reference} has been cancelled. "
                "If payment was made, our team will process your refund promptly."
            )
            await self._dispatch_and_log(
                db=db,
                order=order,
                recipient=order.customer_phone,
                message=message,
            )
        except Exception as exc:
            logger.error(f"Error in notify_order_cancelled: {exc}")

    async def list_logs(
        self,
        db: AsyncSession,
        channel: NotificationChannel | None = None,
        recipient: str | None = None,
        order_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[NotificationLog], int]:
        """Lists paginated notification history for administrative review."""
        query = select(NotificationLog)
        if channel:
            query = query.where(NotificationLog.channel == channel)
        if recipient:
            query = query.where(NotificationLog.recipient.contains(recipient.strip()))
        if order_id:
            query = query.where(NotificationLog.order_id == order_id)

        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar_one()

        offset = (page - 1) * page_size
        stmt = (
            query.order_by(NotificationLog.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        items = (await db.execute(stmt)).scalars().all()
        return list(items), total


notification_service = NotificationService()
