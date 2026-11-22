import math
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.catalog import (
    Category,
    PreorderCampaign,
    Product,
    ProductAvailability,
    ProductImage,
    ProductVariant,
)
from api.schemas.catalog import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    ProductCreate,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
)


def slugify(text: str) -> str:
    """Transforms a string into an SEO-friendly URL slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    slug = re.sub(r"[-\s]+", "-", text).strip("-")
    return slug or "item"


class CatalogService:
    """Business logic service for catalog categories, products, variants, and pre-orders."""

    # ---------------------------------------------------------
    # Category Operations
    # ---------------------------------------------------------
    @staticmethod
    async def list_categories(
        db: AsyncSession,
        only_active: bool = True,
    ) -> list[CategoryResponse]:
        """Lists categories along with active item counts."""
        query = (
            select(Category, func.count(Product.id).label("item_count"))
            .outerjoin(
                Product,
                (Product.category_id == Category.id)
                & (Product.availability_status != ProductAvailability.UNPUBLISHED),
            )
            .group_by(Category.id)
            .order_by(Category.display_order.asc(), Category.name.asc())
        )
        if only_active:
            query = query.where(Category.is_active.is_(True))

        result = await db.execute(query)
        rows = result.all()

        responses: list[CategoryResponse] = []
        for cat, count in rows:
            response = CategoryResponse.model_validate(cat)
            response.item_count = count or 0
            responses.append(response)
        return responses

    @staticmethod
    async def get_category_by_id(db: AsyncSession, category_id: uuid.UUID) -> Category:
        """Retrieves a single category by primary key."""
        category = await db.get(Category, category_id)
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category with id '{category_id}' not found.",
            )
        return category

    @staticmethod
    async def create_category(db: AsyncSession, data: CategoryCreate) -> Category:
        """Creates a new category with a unique slug."""
        target_slug = data.slug.strip() if data.slug else slugify(data.name)
        existing = await db.scalar(select(Category).where(Category.slug == target_slug))
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Category with slug '{target_slug}' already exists.",
            )

        now = datetime.now(UTC)
        category = Category(
            id=uuid.uuid4(),
            name=data.name.strip(),
            slug=target_slug,
            description=data.description,
            image_url=data.image_url,
            display_order=data.display_order,
            is_active=data.is_active,
            created_at=now,
            updated_at=now,
        )
        db.add(category)
        await db.commit()
        return category

    @staticmethod
    async def update_category(
        db: AsyncSession,
        category_id: uuid.UUID,
        data: CategoryUpdate,
    ) -> Category:
        """Updates category properties."""
        category = await CatalogService.get_category_by_id(db, category_id)

        if data.slug is not None:
            new_slug = slugify(data.slug)
            if new_slug != category.slug:
                existing = await db.scalar(
                    select(Category).where(
                        (Category.slug == new_slug) & (Category.id != category_id)
                    )
                )
                if existing:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Category with slug '{new_slug}' already exists.",
                    )
                category.slug = new_slug

        if data.name is not None:
            category.name = data.name.strip()
        if data.description is not None:
            category.description = data.description
        if data.image_url is not None:
            category.image_url = data.image_url
        if data.display_order is not None:
            category.display_order = data.display_order
        if data.is_active is not None:
            category.is_active = data.is_active

        await db.commit()
        await db.refresh(category)
        return category

    @staticmethod
    async def delete_category(db: AsyncSession, category_id: uuid.UUID) -> None:
        """Deletes a category."""
        category = await CatalogService.get_category_by_id(db, category_id)
        await db.delete(category)
        await db.commit()

    # ---------------------------------------------------------
    # Product Operations
    # ---------------------------------------------------------
    @staticmethod
    async def list_products(
        db: AsyncSession,
        category_slug: str | None = None,
        availability: ProductAvailability | None = None,
        search: str | None = None,
        is_featured: bool | None = None,
        page: int = 1,
        page_size: int = 20,
        include_unpublished: bool = False,
    ) -> ProductListResponse:
        """Retrieves paginated, filtered product listings."""
        query = select(Product).options(
            selectinload(Product.category),
            selectinload(Product.variants),
            selectinload(Product.images),
            selectinload(Product.preorder_campaign),
        )

        filters = []
        if not include_unpublished:
            filters.append(
                Product.availability_status != ProductAvailability.UNPUBLISHED
            )

        if category_slug:
            query = query.join(Product.category)
            filters.append(Category.slug == category_slug.lower().strip())

        if availability:
            filters.append(Product.availability_status == availability)

        if is_featured is not None:
            filters.append(Product.is_featured.is_(is_featured))

        if search:
            term = f"%{search.strip()}%"
            filters.append(
                or_(
                    Product.name.ilike(term),
                    Product.description.ilike(term),
                )
            )

        if filters:
            query = query.where(*filters)

        # Count total matches
        count_subquery = select(func.count(Product.id)).select_from(Product)
        if category_slug:
            count_subquery = count_subquery.join(Product.category)
        if filters:
            count_subquery = count_subquery.where(*filters)

        total = await db.scalar(count_subquery) or 0

        # Apply ordering and pagination
        offset = max(0, (page - 1) * page_size)
        query = (
            query.order_by(Product.is_featured.desc(), Product.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )

        result = await db.execute(query)
        products = result.scalars().all()

        pages = math.ceil(total / page_size) if total > 0 else 1
        items = [ProductResponse.model_validate(p) for p in products]

        return ProductListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    @staticmethod
    async def get_product_by_slug(
        db: AsyncSession,
        slug: str,
        include_unpublished: bool = False,
    ) -> Product:
        """Retrieves a single product by slug."""
        query = (
            select(Product)
            .where(Product.slug == slug.lower().strip())
            .options(
                selectinload(Product.category),
                selectinload(Product.variants),
                selectinload(Product.images),
                selectinload(Product.preorder_campaign),
            )
        )
        product = (await db.execute(query)).scalar_one_or_none()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with slug '{slug}' not found.",
            )

        if (
            not include_unpublished
            and product.availability_status == ProductAvailability.UNPUBLISHED
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with slug '{slug}' not found.",
            )

        return product

    @staticmethod
    async def get_product_by_id(
        db: AsyncSession,
        product_id: uuid.UUID,
    ) -> Product:
        """Retrieves a single product by UUID."""
        query = (
            select(Product)
            .where(Product.id == product_id)
            .options(
                selectinload(Product.category),
                selectinload(Product.variants),
                selectinload(Product.images),
                selectinload(Product.preorder_campaign),
            )
        )
        product = (await db.execute(query)).scalar_one_or_none()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with id '{product_id}' not found.",
            )
        return product

    @staticmethod
    async def create_product(
        db: AsyncSession,
        data: ProductCreate,
    ) -> Product:
        """Creates a new product with nested variants, imagery, and pre-order parameters."""
        target_slug = data.slug.strip() if data.slug else slugify(data.name)

        existing = await db.scalar(select(Product).where(Product.slug == target_slug))
        if existing:
            # Suffix with short random hex to avoid collisions
            target_slug = f"{target_slug}-{uuid.uuid4().hex[:6]}"

        if data.category_id:
            cat = await db.get(Category, data.category_id)
            if not cat:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Category '{data.category_id}' does not exist.",
                )

        product_id = uuid.uuid4()
        now = datetime.now(UTC)
        fit = data.details.fit if data.details else None
        fabric = data.details.fabric if data.details else None
        care = data.details.care if data.details else None

        product = Product(
            id=product_id,
            category_id=data.category_id,
            name=data.name.strip(),
            slug=target_slug,
            description=data.description,
            price=Decimal(str(data.price)),
            original_price=Decimal(str(data.original_price))
            if data.original_price is not None
            else None,
            availability_status=data.availability_status,
            is_featured=data.is_featured,
            fit=fit,
            fabric=fabric,
            care=care,
            tags=data.tags,
            offers=data.offers,
            created_at=now,
            updated_at=now,
        )

        # Attach nested variants
        for v in data.variants:
            variant = ProductVariant(
                id=uuid.uuid4(),
                product_id=product_id,
                sku=v.sku.strip(),
                size=v.size.strip().upper(),
                color=v.color.strip(),
                color_hex=v.color_hex.strip(),
                price_override=Decimal(str(v.price_override))
                if v.price_override is not None
                else None,
                stock_quantity=v.stock_quantity,
                is_active=v.is_active,
                created_at=now,
                updated_at=now,
            )
            product.variants.append(variant)

        # Attach nested images
        for idx, img in enumerate(data.images):
            image = ProductImage(
                id=uuid.uuid4(),
                product_id=product_id,
                url=img.url.strip(),
                alt_text=img.alt_text,
                display_order=img.display_order if img.display_order else idx,
                is_primary=img.is_primary if idx > 0 else True,
                created_at=now,
                updated_at=now,
            )
            product.images.append(image)

        # Attach pre-order campaign if present
        if data.preorder_campaign:
            camp = PreorderCampaign(
                id=uuid.uuid4(),
                product_id=product_id,
                order_deadline=data.preorder_campaign.order_deadline,
                expected_delivery_date=data.preorder_campaign.expected_delivery_date,
                max_order_limit=data.preorder_campaign.max_order_limit,
                current_orders_count=0,
                terms_note=data.preorder_campaign.terms_note,
                is_active=data.preorder_campaign.is_active,
                created_at=now,
                updated_at=now,
            )
            product.preorder_campaign = camp

        db.add(product)
        await db.commit()
        return product

    @staticmethod
    async def update_product(
        db: AsyncSession,
        product_id: uuid.UUID,
        data: ProductUpdate,
    ) -> Product:
        """Updates product details, variants, images, or pre-order settings."""
        product = await CatalogService.get_product_by_id(db, product_id)

        if data.name is not None:
            product.name = data.name.strip()
        if data.slug is not None:
            new_slug = slugify(data.slug)
            if new_slug != product.slug:
                existing = await db.scalar(
                    select(Product).where(
                        (Product.slug == new_slug) & (Product.id != product_id)
                    )
                )
                if existing:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Product with slug '{new_slug}' already exists.",
                    )
                product.slug = new_slug
        if data.category_id is not None:
            cat = await db.get(Category, data.category_id)
            if not cat:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Category '{data.category_id}' does not exist.",
                )
            product.category_id = data.category_id
        if data.description is not None:
            product.description = data.description
        if data.price is not None:
            product.price = Decimal(str(data.price))
        if data.original_price is not None:
            product.original_price = Decimal(str(data.original_price))
        if data.availability_status is not None:
            product.availability_status = data.availability_status
        if data.is_featured is not None:
            product.is_featured = data.is_featured

        if data.details is not None:
            if data.details.fit is not None:
                product.fit = data.details.fit
            if data.details.fabric is not None:
                product.fabric = data.details.fabric
            if data.details.care is not None:
                product.care = data.details.care

        if data.tags is not None:
            product.tags = data.tags
        if data.offers is not None:
            product.offers = data.offers

        # Replace variants if provided
        if data.variants is not None:
            product.variants.clear()
            for v in data.variants:
                product.variants.append(
                    ProductVariant(
                        id=uuid.uuid4(),
                        product_id=product_id,
                        sku=v.sku.strip(),
                        size=v.size.strip().upper(),
                        color=v.color.strip(),
                        color_hex=v.color_hex.strip(),
                        price_override=Decimal(str(v.price_override))
                        if v.price_override is not None
                        else None,
                        stock_quantity=v.stock_quantity,
                        is_active=v.is_active,
                    )
                )

        # Replace images if provided
        if data.images is not None:
            product.images.clear()
            for idx, img in enumerate(data.images):
                product.images.append(
                    ProductImage(
                        id=uuid.uuid4(),
                        product_id=product_id,
                        url=img.url.strip(),
                        alt_text=img.alt_text,
                        display_order=img.display_order if img.display_order else idx,
                        is_primary=img.is_primary if idx > 0 else True,
                    )
                )

        # Update or set pre-order campaign
        if data.preorder_campaign is not None:
            if product.preorder_campaign:
                product.preorder_campaign.order_deadline = (
                    data.preorder_campaign.order_deadline
                )
                product.preorder_campaign.expected_delivery_date = (
                    data.preorder_campaign.expected_delivery_date
                )
                product.preorder_campaign.max_order_limit = (
                    data.preorder_campaign.max_order_limit
                )
                product.preorder_campaign.terms_note = data.preorder_campaign.terms_note
                product.preorder_campaign.is_active = data.preorder_campaign.is_active
            else:
                product.preorder_campaign = PreorderCampaign(
                    id=uuid.uuid4(),
                    product_id=product_id,
                    order_deadline=data.preorder_campaign.order_deadline,
                    expected_delivery_date=data.preorder_campaign.expected_delivery_date,
                    max_order_limit=data.preorder_campaign.max_order_limit,
                    terms_note=data.preorder_campaign.terms_note,
                    is_active=data.preorder_campaign.is_active,
                )

        await db.commit()
        return await CatalogService.get_product_by_id(db, product_id)

    @staticmethod
    async def delete_product(db: AsyncSession, product_id: uuid.UUID) -> None:
        """Deletes a product listing and its cascade children."""
        product = await CatalogService.get_product_by_id(db, product_id)
        await db.delete(product)
        await db.commit()
