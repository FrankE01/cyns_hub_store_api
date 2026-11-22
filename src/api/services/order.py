import math
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.catalog import Product, ProductAvailability, ProductVariant
from api.models.order import (
    FulfillmentStatus,
    Order,
    OrderItem,
    OrderStatusHistory,
    PaymentMethod,
    PaymentStatus,
)
from api.schemas.order import (
    OrderCreate,
    OrderListResponse,
    OrderResponse,
    OrderStatusUpdate,
    QuoteItemResponse,
    QuoteRequest,
    QuoteResponse,
)

# Valid state machine transitions
VALID_TRANSITIONS: dict[FulfillmentStatus, set[FulfillmentStatus]] = {
    FulfillmentStatus.AWAITING_PAYMENT: {
        FulfillmentStatus.AWAITING_STOCK,
        FulfillmentStatus.PROCESSING,
        FulfillmentStatus.CANCELLED,
    },
    FulfillmentStatus.AWAITING_STOCK: {
        FulfillmentStatus.PROCESSING,
        FulfillmentStatus.CANCELLED,
    },
    FulfillmentStatus.PROCESSING: {
        FulfillmentStatus.READY_FOR_DISPATCH,
        FulfillmentStatus.CANCELLED,
    },
    FulfillmentStatus.READY_FOR_DISPATCH: {
        FulfillmentStatus.OUT_FOR_DELIVERY,
        FulfillmentStatus.CANCELLED,
    },
    FulfillmentStatus.OUT_FOR_DELIVERY: {
        FulfillmentStatus.COMPLETED,
        FulfillmentStatus.CANCELLED,
    },
    FulfillmentStatus.COMPLETED: set(),  # Terminal state
    FulfillmentStatus.CANCELLED: set(),  # Terminal state
}

ACCRA_DELIVERY_FEE = Decimal("25.00")
OUTSIDE_ACCRA_DELIVERY_FEE = Decimal("50.00")
FREE_DELIVERY_THRESHOLD = Decimal("500.00")


class OrderService:
    """Business logic service for checkout quotes, order lifecycle, and fulfillment state machine."""

    # ---------------------------------------------------------
    # Delivery & Quote Calculation
    # ---------------------------------------------------------
    @staticmethod
    def calculate_delivery_fee(
        delivery_region: str, subtotal: Decimal
    ) -> tuple[Decimal, bool]:
        """Calculates delivery charge based on Ghana region and free delivery threshold."""
        if subtotal >= FREE_DELIVERY_THRESHOLD:
            return Decimal("0.00"), True

        region_lower = delivery_region.lower().strip()
        if "accra" in region_lower:
            return ACCRA_DELIVERY_FEE, False
        return OUTSIDE_ACCRA_DELIVERY_FEE, False

    @staticmethod
    async def calculate_quote(
        db: AsyncSession,
        payload: QuoteRequest,
    ) -> QuoteResponse:
        """Validates checkout cart items, inventory availability, and delivery pricing."""
        items: list[QuoteItemResponse] = []
        subtotal = Decimal("0.00")
        is_pre_order = False
        latest_dispatch_date: datetime | None = None
        validation_errors: list[str] = []

        now = datetime.now(UTC)

        for req_item in payload.items:
            product = await db.get(
                Product,
                req_item.product_id,
                options=[
                    selectinload(Product.variants),
                    selectinload(Product.images),
                    selectinload(Product.preorder_campaign),
                ],
            )
            if (
                not product
                or product.availability_status == ProductAvailability.UNPUBLISHED
            ):
                validation_errors.append(
                    f"Product '{req_item.product_id}' is no longer available."
                )
                continue

            variant: ProductVariant | None = None
            if req_item.variant_id:
                for v in product.variants:
                    if v.id == req_item.variant_id and v.is_active:
                        variant = v
                        break
                if not variant:
                    validation_errors.append(
                        f"Variant '{req_item.variant_id}' for '{product.name}' was not found."
                    )
                    continue
            elif product.variants:
                # Default to first active variant
                for v in product.variants:
                    if v.is_active:
                        variant = v
                        break

            # Check pre-order status
            item_is_preorder = product.is_pre_order
            camp = product.preorder_campaign

            if item_is_preorder and camp and camp.is_active:
                is_pre_order = True
                if camp.order_deadline < now:
                    validation_errors.append(
                        f"Pre-order campaign for '{product.name}' closed on {camp.order_deadline.strftime('%Y-%m-%d')}."
                    )
                if (
                    camp.max_order_limit
                    and (camp.current_orders_count + req_item.quantity)
                    > camp.max_order_limit
                ):
                    validation_errors.append(
                        f"Pre-order limit for '{product.name}' has been reached."
                    )
                if not latest_dispatch_date or (
                    camp.expected_delivery_date > latest_dispatch_date
                ):
                    latest_dispatch_date = camp.expected_delivery_date
            elif variant and variant.stock_quantity < req_item.quantity:
                validation_errors.append(
                    f"Insufficient stock for '{product.name}' ({variant.size} / {variant.color}). Available: {variant.stock_quantity}."
                )

            # Determine price
            unit_price = (
                variant.price_override
                if (variant and variant.price_override is not None)
                else product.price
            )
            item_subtotal = unit_price * req_item.quantity
            subtotal += item_subtotal

            items.append(
                QuoteItemResponse(
                    product_id=product.id,
                    variant_id=variant.id if variant else None,
                    product_name=product.name,
                    product_slug=product.slug,
                    size=variant.size if variant else "Standard",
                    color=variant.color if variant else "Standard",
                    unit_price=unit_price,
                    quantity=req_item.quantity,
                    subtotal=item_subtotal,
                    is_pre_order=item_is_preorder,
                    in_stock=(variant.stock_quantity >= req_item.quantity)
                    if variant
                    else True,
                )
            )

        delivery_fee, free_delivery = OrderService.calculate_delivery_fee(
            payload.delivery_region, subtotal
        )
        total = subtotal + delivery_fee

        if not is_pre_order and not latest_dispatch_date:
            latest_dispatch_date = now + timedelta(days=2)

        return QuoteResponse(
            items=items,
            subtotal=subtotal,
            delivery_fee=delivery_fee,
            total=total,
            is_pre_order=is_pre_order,
            estimated_dispatch_date=latest_dispatch_date,
            free_delivery_applied=free_delivery,
            can_checkout=len(validation_errors) == 0,
            validation_errors=validation_errors,
        )

    # ---------------------------------------------------------
    # Order Creation
    # ---------------------------------------------------------
    @staticmethod
    async def generate_order_reference(db: AsyncSession) -> str:
        """Generates a unique, readable order reference (e.g. CYN-20261122-A8F2)."""
        date_str = datetime.now(UTC).strftime("%Y%m%d")
        for _ in range(10):
            suffix = secrets.token_hex(2).upper()
            ref = f"CYN-{date_str}-{suffix}"
            existing = await db.scalar(select(Order.id).where(Order.reference == ref))
            if not existing:
                return ref
        return f"CYN-{date_str}-{uuid.uuid4().hex[:4].upper()}"

    @staticmethod
    async def create_order(
        db: AsyncSession,
        payload: OrderCreate,
    ) -> Order:
        """Atomically captures an order, updates inventory / pre-order counters, and initializes history."""
        # Validate quote first
        quote_req = QuoteRequest(
            items=[
                {
                    "product_id": i.product_id,
                    "variant_id": i.variant_id,
                    "quantity": i.quantity,
                }
                for i in payload.items
            ],
            delivery_region=payload.delivery_region,
        )
        quote = await OrderService.calculate_quote(db, quote_req)
        if not quote.can_checkout or quote.validation_errors:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Order cannot be placed: {'; '.join(quote.validation_errors)}",
            )

        order_id = uuid.uuid4()
        reference = await OrderService.generate_order_reference(db)
        now = datetime.now(UTC)

        # Initial order status
        if payload.payment_method == PaymentMethod.CASH_ON_DELIVERY:
            initial_fulfillment = (
                FulfillmentStatus.AWAITING_STOCK
                if quote.is_pre_order
                else FulfillmentStatus.PROCESSING
            )
        else:
            initial_fulfillment = FulfillmentStatus.AWAITING_PAYMENT

        order = Order(
            id=order_id,
            reference=reference,
            customer_name=payload.customer_name.strip(),
            customer_phone=payload.customer_phone.strip(),
            customer_email=str(payload.customer_email)
            if payload.customer_email
            else None,
            delivery_region=payload.delivery_region.strip(),
            delivery_address=payload.delivery_address.strip(),
            digital_address=payload.digital_address.strip()
            if payload.digital_address
            else None,
            delivery_notes=payload.delivery_notes,
            subtotal=quote.subtotal,
            delivery_fee=quote.delivery_fee,
            total=quote.total,
            payment_method=payload.payment_method,
            payment_status=PaymentStatus.PENDING,
            fulfillment_status=initial_fulfillment,
            is_pre_order=quote.is_pre_order,
            estimated_dispatch_date=quote.estimated_dispatch_date,
            source_channel=payload.source_channel,
            utm_source=payload.utm_source,
            utm_medium=payload.utm_medium,
            utm_campaign=payload.utm_campaign,
            created_at=now,
            updated_at=now,
        )

        # Reserve inventory and build order items
        for q_item in quote.items:
            product = await db.get(
                Product,
                q_item.product_id,
                options=[
                    selectinload(Product.variants),
                    selectinload(Product.images),
                    selectinload(Product.preorder_campaign),
                ],
            )
            variant: ProductVariant | None = None
            if q_item.variant_id and product:
                for v in product.variants:
                    if v.id == q_item.variant_id:
                        variant = v
                        break

            # Deduct stock for in-stock variant
            if variant and not q_item.is_pre_order:
                variant.stock_quantity = max(
                    0, variant.stock_quantity - q_item.quantity
                )

            # Increment pre-order campaign counter
            if q_item.is_pre_order and product and product.preorder_campaign:
                product.preorder_campaign.current_orders_count += q_item.quantity

            primary_img = (
                product.images[0].url if (product and product.images) else None
            )

            order_item = OrderItem(
                id=uuid.uuid4(),
                order_id=order_id,
                product_id=q_item.product_id,
                variant_id=q_item.variant_id,
                product_name=q_item.product_name,
                product_slug=q_item.product_slug,
                image_url=primary_img,
                variant_sku=variant.sku if variant else None,
                size=q_item.size,
                color=q_item.color,
                unit_price=q_item.unit_price,
                quantity=q_item.quantity,
                subtotal=q_item.subtotal,
                is_pre_order=q_item.is_pre_order,
                created_at=now,
                updated_at=now,
            )
            order.items.append(order_item)

        # Initial status log
        status_log = OrderStatusHistory(
            id=uuid.uuid4(),
            order_id=order_id,
            from_status=None,
            to_status=initial_fulfillment.value,
            notes=f"Order created via {payload.payment_method.value}",
            created_at=now,
        )
        order.status_history.append(status_log)

        db.add(order)
        await db.commit()
        return order

    # ---------------------------------------------------------
    # Order Retrieval & Tracking
    # ---------------------------------------------------------
    @staticmethod
    async def get_order_by_reference(
        db: AsyncSession,
        reference: str,
        phone: str | None = None,
    ) -> Order:
        """Public order tracking endpoint by unique reference and optional phone verification."""
        query = (
            select(Order)
            .where(Order.reference == reference.upper().strip())
            .options(
                selectinload(Order.items),
                selectinload(Order.status_history),
            )
        )
        order = (await db.execute(query)).scalar_one_or_none()
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order '{reference}' was not found.",
            )

        if phone:
            norm_query_phone = phone.replace(" ", "").replace("-", "")
            norm_order_phone = order.customer_phone.replace(" ", "").replace("-", "")
            if not norm_order_phone.endswith(norm_query_phone[-9:]):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Phone number does not match order record.",
                )

        return order

    @staticmethod
    async def get_order_by_id(
        db: AsyncSession,
        order_id: uuid.UUID,
    ) -> Order:
        """Retrieves an order by internal UUID with full relations."""
        query = (
            select(Order)
            .where(Order.id == order_id)
            .options(
                selectinload(Order.items),
                selectinload(Order.status_history),
            )
        )
        order = (await db.execute(query)).scalar_one_or_none()
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order with id '{order_id}' was not found.",
            )
        return order

    @staticmethod
    async def list_orders(
        db: AsyncSession,
        fulfillment_status: FulfillmentStatus | None = None,
        payment_status: PaymentStatus | None = None,
        is_pre_order: bool | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> OrderListResponse:
        """Admin listing of orders with filters and pagination."""
        query = select(Order).options(
            selectinload(Order.items),
            selectinload(Order.status_history),
        )
        filters = []
        if fulfillment_status:
            filters.append(Order.fulfillment_status == fulfillment_status)
        if payment_status:
            filters.append(Order.payment_status == payment_status)
        if is_pre_order is not None:
            filters.append(Order.is_pre_order.is_(is_pre_order))
        if search:
            term = f"%{search.strip()}%"
            filters.append(
                or_(
                    Order.reference.ilike(term),
                    Order.customer_name.ilike(term),
                    Order.customer_phone.ilike(term),
                )
            )

        if filters:
            query = query.where(*filters)

        count_subquery = select(func.count(Order.id)).select_from(Order)
        if filters:
            count_subquery = count_subquery.where(*filters)
        total = await db.scalar(count_subquery) or 0

        offset = max(0, (page - 1) * page_size)
        query = query.order_by(Order.created_at.desc()).offset(offset).limit(page_size)

        result = await db.execute(query)
        orders = result.scalars().all()

        pages = math.ceil(total / page_size) if total > 0 else 1
        items = [OrderResponse.model_validate(o) for o in orders]

        return OrderListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    # ---------------------------------------------------------
    # State Machine & Status Updates
    # ---------------------------------------------------------
    @staticmethod
    async def update_order_status(
        db: AsyncSession,
        order_id: uuid.UUID,
        payload: OrderStatusUpdate,
        changed_by_user_id: uuid.UUID | None = None,
    ) -> Order:
        """Transitions order state, enforces state machine rules, and returns stock if cancelled."""
        order = await OrderService.get_order_by_id(db, order_id)
        current_status = order.fulfillment_status
        target_status = payload.status

        if target_status != current_status:
            allowed_next = VALID_TRANSITIONS.get(current_status, set())
            if target_status not in allowed_next:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Cannot transition order from '{current_status.value}' to '{target_status.value}'. "
                        f"Allowed transitions: {[s.value for s in allowed_next]}."
                    ),
                )

            # If transitioning to CANCELLED, restore stock and decrement pre-order counts
            if target_status == FulfillmentStatus.CANCELLED:
                for item in order.items:
                    if item.variant_id:
                        variant = await db.get(ProductVariant, item.variant_id)
                        if variant and not item.is_pre_order:
                            variant.stock_quantity += item.quantity
                    if item.is_pre_order:
                        prod = await db.get(
                            Product,
                            item.product_id,
                            options=[selectinload(Product.preorder_campaign)],
                        )
                        if prod and prod.preorder_campaign:
                            prod.preorder_campaign.current_orders_count = max(
                                0,
                                prod.preorder_campaign.current_orders_count
                                - item.quantity,
                            )

            now = datetime.now(UTC)
            history_entry = OrderStatusHistory(
                id=uuid.uuid4(),
                order_id=order.id,
                from_status=current_status.value,
                to_status=target_status.value,
                changed_by_user_id=changed_by_user_id,
                notes=payload.notes,
                created_at=now,
            )
            order.status_history.append(history_entry)
            order.fulfillment_status = target_status
            order.updated_at = now

        if payload.payment_status is not None:
            order.payment_status = payload.payment_status
            order.updated_at = datetime.now(UTC)

        await db.commit()
        return order
