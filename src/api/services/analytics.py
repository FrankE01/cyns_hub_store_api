import hashlib
import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.analytics import AnalyticsEvent, EventType
from api.models.catalog import PreorderCampaign, Product, ProductVariant
from api.models.order import (
    FulfillmentStatus,
    Order,
    OrderItem,
    PaymentStatus,
    SourceChannel,
)
from api.schemas.analytics import (
    AcquisitionAnalyticsResponse,
    AcquisitionChannelResponse,
    AnalyticsOverviewResponse,
    CampaignAttributionResponse,
    EventCreate,
    FunnelAnalyticsResponse,
    FunnelStepResponse,
    LowStockVariantResponse,
    PreorderPerformanceResponse,
    ProductAnalyticsResponse,
    SalesTrendBucket,
    TopSellingProductResponse,
)

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service providing event capture, marketing attribution, and business intelligence aggregations."""

    @staticmethod
    def _hash_ip(ip: str | None) -> str | None:
        """Computes a one-way anonymized SHA-256 hash of the client IP address."""
        if not ip:
            return None
        return hashlib.sha256(ip.strip().encode("utf-8")).hexdigest()

    @staticmethod
    def _infer_channel(
        source_channel: SourceChannel | None,
        utm_source: str | None,
        referrer: str | None,
    ) -> SourceChannel:
        """Infers the acquisition channel from UTM parameters and HTTP referrer if not explicitly provided."""
        if source_channel:
            return source_channel

        combined = f"{utm_source or ''} {referrer or ''}".lower()
        if "instagram" in combined:
            return SourceChannel.INSTAGRAM
        if "tiktok" in combined:
            return SourceChannel.TIKTOK
        if "whatsapp" in combined:
            return SourceChannel.WHATSAPP
        return SourceChannel.DIRECT

    @staticmethod
    def _resolve_date_range(
        start_date: datetime | None,
        end_date: datetime | None,
    ) -> tuple[datetime, datetime]:
        """Resolves period bounds, defaulting to the last 30 days if unspecified."""
        resolved_end = end_date or datetime.now(UTC)
        resolved_start = start_date or (resolved_end - timedelta(days=30))
        return resolved_start, resolved_end

    async def record_event(
        self,
        db: AsyncSession,
        event_in: EventCreate,
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> AnalyticsEvent:
        """Persists a single storefront interaction event."""
        channel = self._infer_channel(
            event_in.source_channel,
            event_in.utm_source,
            event_in.referrer,
        )

        event = AnalyticsEvent(
            id=uuid.uuid4(),
            event_type=event_in.event_type,
            session_id=event_in.session_id,
            ip_hash=self._hash_ip(client_ip),
            user_agent=user_agent,
            referrer=event_in.referrer,
            product_id=event_in.product_id,
            product_slug=event_in.product_slug,
            category_id=event_in.category_id,
            source_channel=channel,
            utm_source=event_in.utm_source,
            utm_medium=event_in.utm_medium,
            utm_campaign=event_in.utm_campaign,
            utm_content=event_in.utm_content,
            utm_term=event_in.utm_term,
            event_metadata=event_in.event_metadata,
            created_at=datetime.now(UTC),
        )

        db.add(event)
        await db.commit()
        await db.refresh(event)
        return event

    async def record_events_batch(
        self,
        db: AsyncSession,
        events_in: list[EventCreate],
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> list[AnalyticsEvent]:
        """Persists a batch of storefront interaction events in a single transaction."""
        ip_hash = self._hash_ip(client_ip)
        now = datetime.now(UTC)
        created_events: list[AnalyticsEvent] = []

        for item in events_in:
            channel = self._infer_channel(
                item.source_channel,
                item.utm_source,
                item.referrer,
            )
            event = AnalyticsEvent(
                id=uuid.uuid4(),
                event_type=item.event_type,
                session_id=item.session_id,
                ip_hash=ip_hash,
                user_agent=user_agent,
                referrer=item.referrer,
                product_id=item.product_id,
                product_slug=item.product_slug,
                category_id=item.category_id,
                source_channel=channel,
                utm_source=item.utm_source,
                utm_medium=item.utm_medium,
                utm_campaign=item.utm_campaign,
                utm_content=item.utm_content,
                utm_term=item.utm_term,
                event_metadata=item.event_metadata,
                created_at=now,
            )
            db.add(event)
            created_events.append(event)

        await db.commit()
        for event in created_events:
            await db.refresh(event)
        return created_events

    async def get_overview(
        self,
        db: AsyncSession,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> AnalyticsOverviewResponse:
        """Calculates executive performance overview metrics for a given date range."""
        start_dt, end_dt = self._resolve_date_range(start_date, end_date)

        # Revenue and order volume totals
        revenue_query = select(
            func.coalesce(func.sum(Order.total), Decimal("0.00")),
        ).where(
            Order.payment_status == PaymentStatus.PAID,
            Order.created_at >= start_dt,
            Order.created_at <= end_dt,
        )
        total_revenue: Decimal = (await db.execute(revenue_query)).scalar_one()

        orders_count_query = select(func.count(Order.id)).where(
            Order.created_at >= start_dt,
            Order.created_at <= end_dt,
        )
        total_orders: int = (await db.execute(orders_count_query)).scalar_one()

        paid_orders_query = select(func.count(Order.id)).where(
            Order.payment_status == PaymentStatus.PAID,
            Order.created_at >= start_dt,
            Order.created_at <= end_dt,
        )
        paid_orders: int = (await db.execute(paid_orders_query)).scalar_one()

        pending_orders_query = select(func.count(Order.id)).where(
            Order.payment_status == PaymentStatus.PENDING,
            Order.created_at >= start_dt,
            Order.created_at <= end_dt,
        )
        pending_orders: int = (await db.execute(pending_orders_query)).scalar_one()

        cancelled_orders_query = select(func.count(Order.id)).where(
            Order.fulfillment_status == FulfillmentStatus.CANCELLED,
            Order.created_at >= start_dt,
            Order.created_at <= end_dt,
        )
        cancelled_orders: int = (await db.execute(cancelled_orders_query)).scalar_one()

        # Average Order Value (AOV)
        aov = (
            (total_revenue / Decimal(paid_orders)).quantize(Decimal("0.01"))
            if paid_orders > 0
            else Decimal("0.00")
        )

        # Returning Customer Rate
        customer_counts_subq = (
            select(
                Order.customer_phone,
                func.count(Order.id).label("order_count"),
            )
            .where(
                Order.created_at >= start_dt,
                Order.created_at <= end_dt,
            )
            .group_by(Order.customer_phone)
            .subquery()
        )

        total_customers_q = select(func.count()).select_from(customer_counts_subq)
        returning_customers_q = (
            select(func.count())
            .select_from(customer_counts_subq)
            .where(customer_counts_subq.c.order_count > 1)
        )

        total_customers = (await db.execute(total_customers_q)).scalar_one()
        returning_customers = (await db.execute(returning_customers_q)).scalar_one()

        returning_rate = (
            round((returning_customers / total_customers) * 100, 2)
            if total_customers > 0
            else 0.0
        )

        # Daily sales trend
        trend_query = (
            select(
                cast(Order.created_at, Date).label("order_date"),
                func.coalesce(func.sum(Order.total), Decimal("0.00")).label("revenue"),
                func.count(Order.id).label("orders_count"),
            )
            .where(
                Order.payment_status == PaymentStatus.PAID,
                Order.created_at >= start_dt,
                Order.created_at <= end_dt,
            )
            .group_by(cast(Order.created_at, Date))
            .order_by(cast(Order.created_at, Date).asc())
        )
        trend_rows = (await db.execute(trend_query)).all()
        sales_trend = [
            SalesTrendBucket(
                date=str(row.order_date),
                revenue=Decimal(str(row.revenue)),
                orders_count=row.orders_count,
            )
            for row in trend_rows
        ]

        return AnalyticsOverviewResponse(
            period_start=start_dt,
            period_end=end_dt,
            total_revenue=total_revenue,
            total_orders=total_orders,
            paid_orders=paid_orders,
            pending_orders=pending_orders,
            cancelled_orders=cancelled_orders,
            average_order_value=aov,
            returning_customer_rate=returning_rate,
            sales_trend=sales_trend,
        )

    async def get_acquisition(
        self,
        db: AsyncSession,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> AcquisitionAnalyticsResponse:
        """Aggregates traffic volume, funnel milestones, and revenue by channel and UTM campaign."""
        start_dt, end_dt = self._resolve_date_range(start_date, end_date)

        # 1. Event counts by channel
        events_query = (
            select(
                AnalyticsEvent.source_channel,
                AnalyticsEvent.event_type,
                func.count(AnalyticsEvent.id).label("count"),
            )
            .where(
                AnalyticsEvent.created_at >= start_dt,
                AnalyticsEvent.created_at <= end_dt,
            )
            .group_by(AnalyticsEvent.source_channel, AnalyticsEvent.event_type)
        )
        event_rows = (await db.execute(events_query)).all()

        channel_metrics: dict[str, dict[str, Any]] = {
            c.value: {
                "visits": 0,
                "product_views": 0,
                "add_to_cart_count": 0,
                "checkout_initiated_count": 0,
                "orders_count": 0,
                "revenue": Decimal("0.00"),
            }
            for c in SourceChannel
        }

        for row in event_rows:
            ch_key = (
                row.source_channel.value
                if row.source_channel
                else SourceChannel.DIRECT.value
            )
            if ch_key not in channel_metrics:
                channel_metrics[ch_key] = {
                    "visits": 0,
                    "product_views": 0,
                    "add_to_cart_count": 0,
                    "checkout_initiated_count": 0,
                    "orders_count": 0,
                    "revenue": Decimal("0.00"),
                }

            if row.event_type == EventType.PAGE_VIEW:
                channel_metrics[ch_key]["visits"] += row.count
            elif row.event_type == EventType.PRODUCT_VIEW:
                channel_metrics[ch_key]["product_views"] += row.count
            elif row.event_type == EventType.ADD_TO_CART:
                channel_metrics[ch_key]["add_to_cart_count"] += row.count
            elif row.event_type == EventType.CHECKOUT_INITIATED:
                channel_metrics[ch_key]["checkout_initiated_count"] += row.count

        # 2. Orders and revenue by channel
        order_channel_query = (
            select(
                Order.source_channel,
                func.count(Order.id).label("orders_count"),
                func.coalesce(func.sum(Order.total), Decimal("0.00")).label("revenue"),
            )
            .where(
                Order.payment_status == PaymentStatus.PAID,
                Order.created_at >= start_dt,
                Order.created_at <= end_dt,
            )
            .group_by(Order.source_channel)
        )
        order_rows = (await db.execute(order_channel_query)).all()

        for row in order_rows:
            ch_key = (
                row.source_channel.value
                if row.source_channel
                else SourceChannel.DIRECT.value
            )
            if ch_key not in channel_metrics:
                channel_metrics[ch_key] = {
                    "visits": 0,
                    "product_views": 0,
                    "add_to_cart_count": 0,
                    "checkout_initiated_count": 0,
                    "orders_count": 0,
                    "revenue": Decimal("0.00"),
                }
            channel_metrics[ch_key]["orders_count"] = row.orders_count
            channel_metrics[ch_key]["revenue"] = Decimal(str(row.revenue))

        channels_response = []
        for ch_name, data in channel_metrics.items():
            visits = data["visits"]
            orders = data["orders_count"]
            conv_rate = round((orders / visits * 100), 2) if visits > 0 else 0.0
            channels_response.append(
                AcquisitionChannelResponse(
                    channel=ch_name,
                    visits=visits,
                    product_views=data["product_views"],
                    add_to_cart_count=data["add_to_cart_count"],
                    checkout_initiated_count=data["checkout_initiated_count"],
                    orders_count=orders,
                    revenue=data["revenue"],
                    conversion_rate=conv_rate,
                )
            )

        # 3. UTM Campaigns breakdown
        campaigns_query = (
            select(
                Order.utm_source,
                Order.utm_campaign,
                Order.utm_medium,
                func.count(Order.id).label("orders_count"),
                func.coalesce(func.sum(Order.total), Decimal("0.00")).label("revenue"),
            )
            .where(
                Order.payment_status == PaymentStatus.PAID,
                Order.created_at >= start_dt,
                Order.created_at <= end_dt,
                Order.utm_campaign.isnot(None),
            )
            .group_by(Order.utm_source, Order.utm_campaign, Order.utm_medium)
            .order_by(func.coalesce(func.sum(Order.total), Decimal("0.00")).desc())
        )
        campaign_rows = (await db.execute(campaigns_query)).all()

        campaigns_response = [
            CampaignAttributionResponse(
                utm_source=row.utm_source,
                utm_campaign=row.utm_campaign,
                utm_medium=row.utm_medium,
                visits=0,
                orders_count=row.orders_count,
                revenue=Decimal(str(row.revenue)),
            )
            for row in campaign_rows
        ]

        return AcquisitionAnalyticsResponse(
            period_start=start_dt,
            period_end=end_dt,
            channels=channels_response,
            campaigns=campaigns_response,
        )

    async def get_product_analytics(
        self,
        db: AsyncSession,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 10,
    ) -> ProductAnalyticsResponse:
        """Returns best sellers, pre-order demand progress, and low-stock alerts."""
        start_dt, end_dt = self._resolve_date_range(start_date, end_date)

        # 1. Top Selling Products
        top_sellers_query = (
            select(
                OrderItem.product_name,
                OrderItem.product_slug,
                func.sum(OrderItem.quantity).label("units_sold"),
                func.coalesce(func.sum(OrderItem.subtotal), Decimal("0.00")).label(
                    "revenue"
                ),
            )
            .join(Order, OrderItem.order_id == Order.id)
            .where(
                Order.payment_status == PaymentStatus.PAID,
                Order.created_at >= start_dt,
                Order.created_at <= end_dt,
            )
            .group_by(OrderItem.product_name, OrderItem.product_slug)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(limit)
        )
        top_rows = (await db.execute(top_sellers_query)).all()

        top_sellers = [
            TopSellingProductResponse(
                product_id=uuid.uuid4(),  # Representative identifier for aggregated snapshot
                product_name=row.product_name,
                product_slug=row.product_slug,
                units_sold=int(row.units_sold),
                revenue=Decimal(str(row.revenue)),
            )
            for row in top_rows
        ]

        # 2. Pre-order Campaign Performance
        campaigns_query = (
            select(PreorderCampaign, Product.name)
            .join(Product, PreorderCampaign.product_id == Product.id)
            .where(PreorderCampaign.is_active.is_(True))
        )
        campaign_rows = (await db.execute(campaigns_query)).all()

        preorders = [
            PreorderPerformanceResponse(
                product_id=campaign.product_id,
                product_name=product_name,
                campaign_target=campaign.max_order_limit,
                current_orders=campaign.current_orders_count,
                expected_dispatch_date=campaign.expected_delivery_date,
            )
            for campaign, product_name in campaign_rows
        ]

        # 3. Low stock inventory warnings (stock <= 5)
        stock_query = (
            select(ProductVariant, Product.name)
            .join(Product, ProductVariant.product_id == Product.id)
            .where(
                ProductVariant.is_active.is_(True),
                ProductVariant.stock_quantity <= 5,
            )
            .order_by(ProductVariant.stock_quantity.asc())
            .limit(limit)
        )
        stock_rows = (await db.execute(stock_query)).all()

        low_stock_alerts = [
            LowStockVariantResponse(
                variant_id=variant.id,
                product_name=product_name,
                sku=variant.sku,
                size=variant.size,
                color=variant.color,
                stock_quantity=variant.stock_quantity,
            )
            for variant, product_name in stock_rows
        ]

        return ProductAnalyticsResponse(
            period_start=start_dt,
            period_end=end_dt,
            top_selling_products=top_sellers,
            preorder_performance=preorders,
            low_stock_alerts=low_stock_alerts,
        )

    async def get_funnel(
        self,
        db: AsyncSession,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> FunnelAnalyticsResponse:
        """Builds multi-step conversion funnel with drop-off percentages."""
        start_dt, end_dt = self._resolve_date_range(start_date, end_date)

        event_counts_query = (
            select(
                AnalyticsEvent.event_type,
                func.count(AnalyticsEvent.id).label("count"),
            )
            .where(
                AnalyticsEvent.created_at >= start_dt,
                AnalyticsEvent.created_at <= end_dt,
            )
            .group_by(AnalyticsEvent.event_type)
        )
        rows = (await db.execute(event_counts_query)).all()
        counts_by_type = {row.event_type: row.count for row in rows}

        funnel_definitions = [
            (EventType.PAGE_VIEW, "Storefront Visits"),
            (EventType.PRODUCT_VIEW, "Product Views"),
            (EventType.ADD_TO_CART, "Added to Cart"),
            (EventType.CHECKOUT_INITIATED, "Checkout Initiated"),
            (EventType.ORDER_COMPLETED, "Orders Completed"),
        ]

        steps: list[FunnelStepResponse] = []
        top_count = counts_by_type.get(EventType.PAGE_VIEW, 0)
        previous_count = top_count

        for idx, (etype, label) in enumerate(funnel_definitions):
            count = counts_by_type.get(etype, 0)

            if idx == 0:
                conv_prev = 100.0 if count > 0 else 0.0
                conv_top = 100.0 if count > 0 else 0.0
                previous_count = count
            else:
                conv_prev = (
                    round((count / previous_count * 100), 2)
                    if previous_count > 0
                    else 0.0
                )
                conv_top = round((count / top_count * 100), 2) if top_count > 0 else 0.0
                previous_count = count

            steps.append(
                FunnelStepResponse(
                    step=label,
                    count=count,
                    conversion_from_previous=conv_prev,
                    conversion_from_top=conv_top,
                )
            )

        return FunnelAnalyticsResponse(
            period_start=start_dt,
            period_end=end_dt,
            steps=steps,
        )


analytics_service = AnalyticsService()
