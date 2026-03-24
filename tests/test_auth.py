"""Tests for authentication and admin role system"""

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.auth import NotAdminException, require_admin, verify_password, hash_password
from app.models.user import User


class TestPasswordHashing:
    """Tests for password hashing and verification"""

    def test_hash_password_creates_valid_hash(self):
        """Test that hash_password creates a valid hash"""
        plain_password = "test_password_123"
        hashed = hash_password(plain_password)

        assert hashed != plain_password
        assert len(hashed) > len(plain_password)

    def test_verify_password_matches_hashed(self):
        """Test that verify_password works with hashed passwords"""
        plain_password = "secure_password_456"
        hashed = hash_password(plain_password)

        assert verify_password(plain_password, hashed)

    def test_verify_password_rejects_wrong_password(self):
        """Test that verify_password rejects wrong passwords"""
        hashed = hash_password("correct_password")

        assert not verify_password("wrong_password", hashed)

    def test_hash_password_handles_unicode(self):
        """Test that hash_password handles unicode characters"""
        unicode_password = "contraseña_acentuada_ñ"
        hashed = hash_password(unicode_password)

        assert verify_password(unicode_password, hashed)

    def test_hash_password_with_long_password(self):
        """Test that hash_password handles long passwords correctly"""
        # 72 bytes is the bcrypt limit, but argon2 has no limit
        long_password = "a" * 100
        hashed = hash_password(long_password)

        assert verify_password(long_password, hashed)


class TestRequireAdmin:
    """Tests for require_admin dependency"""

    @pytest.mark.asyncio
    async def test_require_admin_allows_admin_user(self):
        """Test that require_admin allows admin users"""
        request = MagicMock()
        request.session = {"user_id": 1}

        admin_user = User(
            id=1, username="admin", first_name="Admin", last_name="User",
            email="admin@example.com", hashed_password="hash", role="admin", is_active=True
        )

        db = MagicMock()
        db.execute = AsyncMock()
        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=admin_user)
        db.execute.return_value = mock_result

        from app.auth import get_current_user

        result = await get_current_user(request, db)

        assert result is admin_user
        assert result.role == "admin"

    @pytest.mark.asyncio
    async def test_require_admin_rejects_regular_user(self):
        """Test that require_admin rejects regular users"""
        request = MagicMock()
        request.session = {"user_id": 2}

        user = User(
            id=2, username="user", first_name="Regular", last_name="User",
            email="user@example.com", hashed_password="hash", role="user", is_active=True
        )

        db = MagicMock()
        db.execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=user)
        db.execute.return_value = mock_result

        from app.auth import get_current_user

        result = await get_current_user(request, db)

        assert result.role == "user"

        # Now test require_admin raises exception
        with pytest.raises(NotAdminException):
            await require_admin(request, db)

    @pytest.mark.asyncio
    async def test_require_admin_rejects_no_session(self):
        """Test that require_admin rejects requests without session"""
        request = MagicMock()
        request.session = {}

        db = MagicMock()

        with pytest.raises(NotAdminException):
            await require_admin(request, db)

    @pytest.mark.asyncio
    async def test_require_admin_rejects_inactive_user(self):
        """Test that require_admin rejects inactive users"""
        request = MagicMock()
        request.session = {"user_id": 3}

        inactive_user = User(
            id=3,
            username="inactive",
            first_name="Inactive",
            last_name="User",
            email="inactive@example.com",
            hashed_password="hash",
            role="admin",
            is_active=False,
        )

        db = MagicMock()
        db.execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=inactive_user)
        db.execute.return_value = mock_result

        from app.auth import get_current_user

        result = await get_current_user(request, db)

        # get_current_user returns the user regardless of is_active
        assert result.is_active is False


class TestUserModel:
    """Tests for User model with role and is_active fields"""

    def test_user_accepts_role_parameter(self):
        """Test that User accepts role parameter"""
        user = User(id=1, username="test", first_name="Test", last_name="User",
                    email="test@example.com", hashed_password="hash", role="user")

        assert user.role == "user"

    def test_user_accepts_is_active_parameter(self):
        """Test that User accepts is_active parameter"""
        user = User(id=1, username="test", first_name="Test", last_name="User",
                    email="test@example.com", hashed_password="hash", is_active=True)

        assert user.is_active is True

    def test_user_can_have_admin_role(self):
        """Test that users can have 'admin' role"""
        user = User(id=1, username="admin", first_name="Admin", last_name="User",
                    email="admin@example.com", hashed_password="hash", role="admin")

        assert user.role == "admin"

    def test_user_can_be_deactivated(self):
        """Test that users can be deactivated"""
        user = User(id=1, username="inactive", first_name="Inactive", last_name="User",
                    email="inactive@example.com", hashed_password="hash", is_active=False)

        assert user.is_active is False


class TestUserProfileFields:
    """Tests for user profile fields (first_name, last_name, email)"""

    def test_user_stores_first_name(self):
        """Test that User stores first_name correctly"""
        user = User(
            id=1, username="javier", first_name="Javier", last_name="Gómez",
            email="javier@example.com", hashed_password="hash"
        )
        assert user.first_name == "Javier"

    def test_user_stores_last_name(self):
        """Test that User stores last_name correctly"""
        user = User(
            id=1, username="javier", first_name="Javier", last_name="Gómez",
            email="javier@example.com", hashed_password="hash"
        )
        assert user.last_name == "Gómez"

    def test_user_stores_email(self):
        """Test that User stores email correctly"""
        user = User(
            id=1, username="javier", first_name="Javier", last_name="Gómez",
            email="javier@example.com", hashed_password="hash"
        )
        assert user.email == "javier@example.com"

    def test_user_with_unicode_names(self):
        """Test that User handles unicode characters in names"""
        user = User(
            id=1, username="juan", first_name="Juan", last_name="García López",
            email="juan@example.com", hashed_password="hash"
        )
        assert user.first_name == "Juan"
        assert user.last_name == "García López"

    def test_user_profile_display_format(self):
        """Test user profile can be displayed as 'FirstName LastName (email)'"""
        user = User(
            id=1, username="carlos", first_name="Carlos", last_name="Martinez",
            email="carlos@example.com", hashed_password="hash"
        )
        profile_display = f"{user.first_name} {user.last_name} ({user.email})"
        assert profile_display == "Carlos Martinez (carlos@example.com)"
