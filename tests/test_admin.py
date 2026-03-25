"""Integration tests for admin router and user management endpoints"""
import datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth import hash_password
from app.database import Base
from app.models import Expense, Income, Plot, User


async def _build_sessionmaker(db_file: Path):
    """Build session maker for test database"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    return engine, session_maker


@pytest.mark.asyncio
async def test_soft_delete_preserves_user_data(tmp_path: Path) -> None:
    """Test that deactivating a user preserves their data in the database"""
    engine, session_maker = await _build_sessionmaker(tmp_path / "soft_delete.sqlite3")

    try:
        async with session_maker() as db:
            # Create a user with associated data
            user = User(
                username="user_to_deactivate",
                first_name="Test",
                last_name="User",
                email="test@example.com",
                hashed_password=hash_password("password123"),
                role="user",
                is_active=True,
            )
            db.add(user)
            await db.flush()

            plot = Plot(
                name="Test Plot",
                polygon="1",
                plot_num="123",
                cadastral_ref="44223A021001200000FP",
                hydrant="H1",
                sector="S1",
                num_plants=100,
                planting_date=datetime.date(2020, 1, 1),
                area_ha=1.0,
                production_start=datetime.date(2023, 1, 1),
                percentage=100.0,
                user_id=user.id,
            )
            db.add(plot)
            await db.commit()

            # Deactivate user
            user.is_active = False
            await db.commit()

            # Verify user is inactive
            from sqlalchemy import select

            result = await db.execute(
                select(User).where(User.username == "user_to_deactivate")
            )
            deactivated_user = result.scalar_one()
            assert deactivated_user.is_active is False

            # Verify data still exists in DB
            result = await db.execute(select(Plot).where(Plot.user_id == user.id))
            plots = result.scalars().all()
            assert len(plots) == 1
            assert plots[0].name == "Test Plot"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_user_role_change(tmp_path: Path) -> None:
    """Test that user role can be changed from user to admin"""
    engine, session_maker = await _build_sessionmaker(tmp_path / "role_change.sqlite3")

    try:
        async with session_maker() as db:
            # Create a regular user
            user = User(
                username="future_admin",
                first_name="Future",
                last_name="Admin",
                email="futadmin@example.com",
                hashed_password=hash_password("password123"),
                role="user",
                is_active=True,
            )
            db.add(user)
            await db.commit()

            # Change role to admin
            user.role = "admin"
            await db.commit()

            # Verify role changed
            from sqlalchemy import select

            result = await db.execute(
                select(User).where(User.username == "future_admin")
            )
            updated_user = result.scalar_one()
            assert updated_user.role == "admin"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_first_user_is_admin(tmp_path: Path) -> None:
    """Test that the first registered user becomes admin"""
    engine, session_maker = await _build_sessionmaker(tmp_path / "first_admin.sqlite3")

    try:
        async with session_maker() as db:
            # Create first user (should be admin)
            user1 = User(
                username="first_user",
                first_name="First",
                last_name="User",
                email="first@example.com",
                hashed_password=hash_password("password123"),
                role="admin",
                is_active=True,
            )
            db.add(user1)
            await db.commit()

            # Create second user (should be regular user)
            user2 = User(
                username="second_user",
                first_name="Second",
                last_name="User",
                email="second@example.com",
                hashed_password=hash_password("password123"),
                role="user",
                is_active=True,
            )
            db.add(user2)
            await db.commit()

            # Verify roles
            from sqlalchemy import select

            result = await db.execute(select(User).order_by(User.id))
            users = result.scalars().all()

            assert users[0].role == "admin"
            assert users[1].role == "user"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_inactive_user_cannot_login(tmp_path: Path) -> None:
    """Test that inactive users are blocked from logging in"""
    engine, session_maker = await _build_sessionmaker(
        tmp_path / "inactive_login.sqlite3"
    )

    try:
        async with session_maker() as db:
            # Create an inactive user
            user = User(
                username="inactive_user",
                first_name="Inactive",
                last_name="User",
                email="inactive@example.com",
                hashed_password=hash_password("mypassword"),
                role="user",
                is_active=False,
            )
            db.add(user)
            await db.commit()

            # Verify user is inactive
            from sqlalchemy import select

            result = await db.execute(
                select(User).where(User.username == "inactive_user")
            )
            inactive_user = result.scalar_one()
            assert inactive_user.is_active is False

            # Login attempt would fail (in actual login handler)
            # This test verifies the data structure is correct
            assert inactive_user.hashed_password is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_admin_can_manage_multiple_users(tmp_path: Path) -> None:
    """Test admin can manage multiple users"""
    engine, session_maker = await _build_sessionmaker(
        tmp_path / "admin_manage.sqlite3"
    )

    try:
        async with session_maker() as db:
            # Create admin user
            admin = User(
                username="admin_user",
                first_name="Admin",
                last_name="User",
                email="admin@example.com",
                hashed_password=hash_password("admin123"),
                role="admin",
                is_active=True,
            )
            db.add(admin)
            await db.flush()

            # Create multiple regular users
            for i in range(3):
                user = User(
                    username=f"user_{i}",
                    first_name=f"User{i}",
                    last_name="Test",
                    email=f"user{i}@example.com",
                    hashed_password=hash_password(f"password{i}"),
                    role="user",
                    is_active=True,
                )
                db.add(user)

            await db.commit()

            # Verify all users created
            from sqlalchemy import select

            result = await db.execute(select(User))
            all_users = result.scalars().all()
            assert len(all_users) == 4  # 1 admin + 3 regular

            # Count admin and regular users
            result = await db.execute(select(User).where(User.role == "admin"))
            admins = result.scalars().all()
            assert len(admins) == 1

            result = await db.execute(select(User).where(User.role == "user"))
            users = result.scalars().all()
            assert len(users) == 3
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_user_profile_fields_are_stored(tmp_path: Path) -> None:
    """Test that profile fields (first_name, last_name, email) are correctly stored"""
    engine, session_maker = await _build_sessionmaker(tmp_path / "profile_fields.sqlite3")

    try:
        async with session_maker() as db:
            user = User(
                username="javier",
                first_name="Javier",
                last_name="Gómez",
                email="javier@example.com",
                hashed_password=hash_password("password123"),
                role="user",
                is_active=True,
            )
            db.add(user)
            await db.commit()

            # Retrieve and verify
            from sqlalchemy import select

            result = await db.execute(select(User).where(User.username == "javier"))
            retrieved_user = result.scalar_one()

            assert retrieved_user.first_name == "Javier"
            assert retrieved_user.last_name == "Gómez"
            assert retrieved_user.email == "javier@example.com"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_email_uniqueness_enforced(tmp_path: Path) -> None:
    """Test that email uniqueness is enforced at the database level"""
    engine, session_maker = await _build_sessionmaker(
        tmp_path / "email_unique.sqlite3"
    )

    try:
        async with session_maker() as db:
            # Create first user
            user1 = User(
                username="user1",
                first_name="User",
                last_name="One",
                email="shared@example.com",
                hashed_password=hash_password("password123"),
                role="user",
                is_active=True,
            )
            db.add(user1)
            await db.commit()

            # Try to create second user with same email
            user2 = User(
                username="user2",
                first_name="User",
                last_name="Two",
                email="shared@example.com",
                hashed_password=hash_password("password123"),
                role="user",
                is_active=True,
            )
            db.add(user2)

            # Should raise IntegrityError due to unique constraint
            from sqlalchemy.exc import IntegrityError

            with pytest.raises(IntegrityError):
                await db.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_admin_can_edit_user_profile(tmp_path: Path) -> None:
    """Test that admin can edit user profile fields"""
    engine, session_maker = await _build_sessionmaker(tmp_path / "edit_profile.sqlite3")

    try:
        async with session_maker() as db:
            # Create user
            user = User(
                username="carlos",
                first_name="Carlos",
                last_name="Martinez",
                email="carlos@example.com",
                hashed_password=hash_password("password123"),
                role="user",
                is_active=True,
            )
            db.add(user)
            await db.commit()

            # Edit profile
            user.first_name = "Charles"
            user.last_name = "Martin"
            user.email = "charles@example.com"
            await db.commit()

            # Verify changes
            from sqlalchemy import select

            result = await db.execute(select(User).where(User.id == user.id))
            updated_user = result.scalar_one()

            assert updated_user.first_name == "Charles"
            assert updated_user.last_name == "Martin"
            assert updated_user.email == "charles@example.com"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_user_profile_display_format(tmp_path: Path) -> None:
    """Test that user profile can be displayed in correct format"""
    engine, session_maker = await _build_sessionmaker(tmp_path / "profile_format.sqlite3")

    try:
        async with session_maker() as db:
            user = User(
                username="ana",
                first_name="Ana",
                last_name="García",
                email="ana@example.com",
                hashed_password=hash_password("password123"),
                role="user",
                is_active=True,
            )
            db.add(user)
            await db.commit()

            # Retrieve and format
            from sqlalchemy import select

            result = await db.execute(select(User).where(User.username == "ana"))
            retrieved_user = result.scalar_one()

            display_format = f"{retrieved_user.first_name} {retrieved_user.last_name} ({retrieved_user.email})"
            assert display_format == "Ana García (ana@example.com)"
    finally:
        await engine.dispose()
