import asyncio
import getpass
import sys

from sqlalchemy import select

from api.core.database import AsyncSessionLocal, init_db
from api.core.security import hash_password
from api.models.user import User, UserRole


async def create_admin(email: str, password: str, full_name: str) -> None:
    """Creates a new administrator account in the database."""
    await init_db()
    async with AsyncSessionLocal() as session:
        query = select(User).where(User.email == email.lower().strip())
        existing = (await session.execute(query)).scalar_one_or_none()
        if existing:
            print(f"Error: User with email '{email}' already exists.")
            sys.exit(1)

        user = User(
            email=email.lower().strip(),
            hashed_password=hash_password(password),
            full_name=full_name.strip(),
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        print(f"Successfully created administrator user: {email}")


def create_admin_cli() -> None:
    """Interactive command-line tool to bootstrap an administrator account."""
    print("=== Create Cyn's Hub Store Administrator ===")
    email = input("Email: ").strip()
    if not email:
        print("Email cannot be empty.")
        sys.exit(1)
    full_name = input("Full Name: ").strip()
    if not full_name:
        print("Full name cannot be empty.")
        sys.exit(1)
    password = getpass.getpass("Password: ")
    if len(password) < 8:
        print("Password must be at least 8 characters.")
        sys.exit(1)
    confirm = getpass.getpass("Confirm Password: ")
    if password != confirm:
        print("Passwords do not match.")
        sys.exit(1)

    asyncio.run(create_admin(email, password, full_name))


if __name__ == "__main__":
    create_admin_cli()
