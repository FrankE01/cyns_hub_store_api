import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import settings
from api.models.order import (
    FulfillmentStatus,
    Order,
    OrderStatusHistory,
    PaymentMethod,
    PaymentStatus,
)
from api.models.payment import Payment
from api.models.user import User
from api.services.notification import notification_service
from api.services.paystack import paystack_service

logger = logging.getLogger(__name__)


class PaymentService:
    """Service handling multi-channel payment initialization, verification, and webhooks."""

    async def initialize_paystack_payment(
        self,
        db: AsyncSession,
        order_reference: str,
        callback_url: str | None = None,
    ) -> Payment:
        """Initializes a Paystack payment session for an order."""
        stmt = select(Order).where(Order.reference == order_reference.strip().upper())
        order = (await db.execute(stmt)).scalar_one_or_none()

        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order '{order_reference}' not found",
            )

        if order.payment_status == PaymentStatus.PAID:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Order has already been paid",
            )

        if order.fulfillment_status == FulfillmentStatus.CANCELLED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot initialize payment for a cancelled order",
            )

        # Unique reference per transaction attempt to prevent Paystack duplicates
        gateway_ref = f"PAY-{order.reference}-{uuid.uuid4().hex[:6].upper()}"
        amount_pesewas = int(round(float(order.total) * 100))

        # Email fallback if customer only provided phone number
        customer_email = order.customer_email
        if not customer_email:
            cleaned_phone = order.customer_phone.replace("+", "").replace(" ", "")
            customer_email = f"customer_{cleaned_phone}@cynshub.com"

        metadata = {
            "order_id": str(order.id),
            "order_reference": order.reference,
            "customer_phone": order.customer_phone,
            "customer_name": order.customer_name,
        }

        auth_data = await paystack_service.initialize_transaction(
            email=customer_email,
            amount_pesewas=amount_pesewas,
            reference=gateway_ref,
            callback_url=callback_url or settings.paystack.callback_url,
            metadata=metadata,
        )

        payment = Payment(
            id=uuid.uuid4(),
            order_id=order.id,
            amount=order.total,
            currency="GHS",
            payment_method=PaymentMethod.MOMO_PAYSTACK,
            payment_status=PaymentStatus.PENDING,
            provider="paystack",
            provider_reference=gateway_ref,
            access_code=auth_data.get("access_code"),
            authorization_url=auth_data.get("authorization_url"),
            customer_phone=order.customer_phone,
            provider_metadata=auth_data,
        )

        db.add(payment)
        await db.commit()
        await db.refresh(payment)
        return payment

    async def verify_paystack_payment(
        self,
        db: AsyncSession,
        reference: str,
    ) -> Payment:
        """Verifies transaction outcome with Paystack API and updates order state."""
        stmt = select(Payment).where(Payment.provider_reference == reference.strip())
        payment = (await db.execute(stmt)).scalar_one_or_none()

        if not payment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Payment reference '{reference}' not found",
            )

        if payment.payment_status == PaymentStatus.PAID:
            return payment

        verification_data = await paystack_service.verify_transaction(reference)
        gateway_status = verification_data.get("status")

        if gateway_status == "success":
            payment.payment_status = PaymentStatus.PAID
            payment.paid_at = datetime.now(UTC)
            payment.provider_metadata = verification_data

            order = await db.get(Order, payment.order_id)
            if order:
                from_status = order.fulfillment_status
                order.payment_status = PaymentStatus.PAID
                if order.is_pre_order:
                    order.fulfillment_status = FulfillmentStatus.AWAITING_STOCK
                else:
                    order.fulfillment_status = FulfillmentStatus.PROCESSING

                history = OrderStatusHistory(
                    order_id=order.id,
                    from_status=str(from_status),
                    to_status=str(order.fulfillment_status),
                    notes=f"Payment verified via Paystack ({reference})",
                )
                db.add(history)

            await db.commit()
            await db.refresh(payment)
            if order:
                await notification_service.notify_payment_confirmed(db, order)
            return payment
        else:
            payment.payment_status = PaymentStatus.FAILED
            payment.provider_metadata = verification_data
            await db.commit()
            await db.refresh(payment)
            if order:
                await notification_service.notify_payment_confirmed(db, order)
            return payment

    async def process_paystack_webhook(
        self,
        db: AsyncSession,
        event_payload: dict[str, Any],
    ) -> Payment | None:
        """Processes verified Paystack webhook event idempotently."""
        event_type = event_payload.get("event")
        if event_type != "charge.success":
            logger.info(f"Ignoring unhandled Paystack event: {event_type}")
            return None

        data = event_payload.get("data", {})
        reference = data.get("reference")
        if not reference:
            logger.warning("Paystack webhook received without reference")
            return None

        stmt = select(Payment).where(Payment.provider_reference == reference)
        payment = (await db.execute(stmt)).scalar_one_or_none()

        if payment and payment.payment_status == PaymentStatus.PAID:
            logger.info(
                f"Paystack payment {reference} is already processed. Idempotent return."
            )
            return payment

        order: Order | None = None
        if payment:
            payment.payment_status = PaymentStatus.PAID
            payment.paid_at = datetime.now(UTC)
            payment.provider_metadata = data
            order = await db.get(Order, payment.order_id)
        else:
            # Payment initiated outside standard flow or reference mismatch; locate via metadata
            metadata = data.get("metadata", {})
            order_id_str = metadata.get("order_id")
            order_ref = metadata.get("order_reference")

            if order_id_str:
                try:
                    order = await db.get(Order, uuid.UUID(order_id_str))
                except (ValueError, TypeError):
                    order = None
            elif order_ref:
                stmt_order = select(Order).where(Order.reference == order_ref)
                order = (await db.execute(stmt_order)).scalar_one_or_none()

            if not order:
                logger.warning(
                    f"Paystack webhook received for untracked order (ref: {reference})"
                )
                return None

            paid_amount = Decimal(str(data.get("amount", 0))) / Decimal("100")
            payment = Payment(
                id=uuid.uuid4(),
                order_id=order.id,
                amount=paid_amount,
                currency=data.get("currency", "GHS"),
                payment_method=PaymentMethod.MOMO_PAYSTACK,
                payment_status=PaymentStatus.PAID,
                provider="paystack",
                provider_reference=reference,
                paid_at=datetime.now(UTC),
                provider_metadata=data,
            )
            db.add(payment)

        if order:
            from_status = order.fulfillment_status
            order.payment_status = PaymentStatus.PAID
            if order.is_pre_order:
                order.fulfillment_status = FulfillmentStatus.AWAITING_STOCK
            else:
                order.fulfillment_status = FulfillmentStatus.PROCESSING

            history = OrderStatusHistory(
                order_id=order.id,
                from_status=str(from_status),
                to_status=str(order.fulfillment_status),
                notes=f"Payment confirmed via Paystack webhook ({reference})",
            )
            db.add(history)

        await db.commit()
        if payment:
            await db.refresh(payment)
        if order:
            await notification_service.notify_payment_confirmed(db, order)
        return payment

    async def submit_manual_payment(
        self,
        db: AsyncSession,
        order_reference: str,
        transaction_reference: str,
        sender_phone: str | None = None,
        notes: str | None = None,
    ) -> Payment:
        """Customer submission of direct Mobile Money or Bank deposit receipt."""
        stmt = select(Order).where(Order.reference == order_reference.strip().upper())
        order = (await db.execute(stmt)).scalar_one_or_none()

        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order '{order_reference}' not found",
            )

        if order.payment_status == PaymentStatus.PAID:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Order has already been paid",
            )

        if order.fulfillment_status == FulfillmentStatus.CANCELLED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot submit payment for a cancelled order",
            )

        tx_ref = transaction_reference.strip()
        existing_stmt = select(Payment).where(Payment.provider_reference == tx_ref)
        existing = (await db.execute(existing_stmt)).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Transaction reference '{tx_ref}' has already been submitted",
            )

        payment = Payment(
            id=uuid.uuid4(),
            order_id=order.id,
            amount=order.total,
            currency="GHS",
            payment_method=PaymentMethod.DIRECT_MOMO,
            payment_status=PaymentStatus.PENDING,
            provider="manual_momo",
            provider_reference=tx_ref,
            customer_phone=sender_phone or order.customer_phone,
            notes=notes,
        )
        db.add(payment)

        history = OrderStatusHistory(
            order_id=order.id,
            from_status=str(order.fulfillment_status),
            to_status=str(order.fulfillment_status),
            notes=f"Customer submitted direct payment reference: {tx_ref}",
        )
        db.add(history)

        await db.commit()
        await db.refresh(payment)
        return payment

    async def verify_manual_payment(
        self,
        db: AsyncSession,
        payment_id: uuid.UUID,
        admin_user: User,
        notes: str | None = None,
    ) -> Payment:
        """Admin confirmation of manual mobile money deposit."""
        payment = await db.get(Payment, payment_id)
        if not payment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Payment '{payment_id}' not found",
            )

        if payment.payment_status == PaymentStatus.PAID:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment is already verified",
            )

        payment.payment_status = PaymentStatus.PAID
        payment.paid_at = datetime.now(UTC)
        if notes:
            admin_note = f"[Admin verified by {admin_user.email}]: {notes}"
            payment.notes = (
                f"{payment.notes}\n{admin_note}" if payment.notes else admin_note
            )

        order = await db.get(Order, payment.order_id)
        if order:
            from_status = order.fulfillment_status
            order.payment_status = PaymentStatus.PAID
            if order.is_pre_order:
                order.fulfillment_status = FulfillmentStatus.AWAITING_STOCK
            else:
                order.fulfillment_status = FulfillmentStatus.PROCESSING

            history = OrderStatusHistory(
                order_id=order.id,
                from_status=str(from_status),
                to_status=str(order.fulfillment_status),
                notes=f"Manual payment verified by admin ({admin_user.email})",
                changed_by_user_id=admin_user.id,
            )
            db.add(history)

        await db.commit()
        await db.refresh(payment)
        return payment

    async def reject_manual_payment(
        self,
        db: AsyncSession,
        payment_id: uuid.UUID,
        admin_user: User,
        reason: str,
    ) -> Payment:
        """Admin rejection of invalid manual payment submission."""
        payment = await db.get(Payment, payment_id)
        if not payment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Payment '{payment_id}' not found",
            )

        if payment.payment_status == PaymentStatus.PAID:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot reject an already verified payment",
            )

        payment.payment_status = PaymentStatus.FAILED
        admin_note = f"[Admin rejected by {admin_user.email}]: {reason}"
        payment.notes = (
            f"{payment.notes}\n{admin_note}" if payment.notes else admin_note
        )

        order = await db.get(Order, payment.order_id)
        if order:
            history = OrderStatusHistory(
                order_id=order.id,
                from_status=str(order.fulfillment_status),
                to_status=str(order.fulfillment_status),
                notes=f"Manual payment rejected by admin ({admin_user.email}): {reason}",
                changed_by_user_id=admin_user.id,
            )
            db.add(history)

        await db.commit()
        await db.refresh(payment)
        return payment

    async def get_payment_by_id(
        self,
        db: AsyncSession,
        payment_id: uuid.UUID,
    ) -> Payment | None:
        """Retrieves a single payment transaction by ID."""
        return await db.get(Payment, payment_id)

    async def list_payments(
        self,
        db: AsyncSession,
        status_filter: PaymentStatus | None = None,
        provider: str | None = None,
        order_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Payment], int]:
        """Lists and filters payment transactions with pagination."""
        query = select(Payment)

        if status_filter:
            query = query.where(Payment.payment_status == status_filter)
        if provider:
            query = query.where(Payment.provider == provider)
        if order_id:
            query = query.where(Payment.order_id == order_id)

        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar_one()

        offset = (page - 1) * page_size
        stmt = query.order_by(Payment.created_at.desc()).offset(offset).limit(page_size)
        results = (await db.execute(stmt)).scalars().all()

        return list(results), total


payment_service = PaymentService()
