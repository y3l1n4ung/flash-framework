import pytest
from flash_authentication.hasher import hash_password, verify_password


class TestHasher:
    def test_hash_password_success(self):
        """Ensure hashing returns a valid Argon2 string."""
        raw = "MySecretPassword123!"
        hashed = hash_password(raw)

        assert hashed != raw
        assert len(hashed) > 20
        assert "$argon2" in hashed

    def test_hash_empty_password_fails(self):
        """Ensure hashing empty strings raises ValueError."""
        with pytest.raises(ValueError, match="Password cannot be empty"):
            hash_password("")

    def test_verify_password_match(self):
        """Ensure verify returns True for correct password."""
        raw = "secret"
        hashed = hash_password(raw)
        assert verify_password(hashed, raw) is True

    def test_verify_password_mismatch(self):
        """Ensure verify returns False for incorrect password."""
        raw = "secret"
        hashed = hash_password(raw)
        assert verify_password(hashed, "wrong_secret") is False

    def test_verify_malformed_hash(self):
        """Ensure verify gracefully handles invalid hash strings (returns False)."""
        assert verify_password("not_a_valid_hash", "secret") is False
        assert verify_password("", "secret") is False
