from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password cannot be empty")
    return _ph.hash(password)


def verify_password(hash: str, password: str) -> bool:
    try:
        return _ph.verify(hash, password)
    except (VerifyMismatchError, Exception):
        return False
