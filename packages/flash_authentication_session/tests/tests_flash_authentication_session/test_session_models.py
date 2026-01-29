from flash_authentication_session import models


def test_user_session():
    assert models.UserSession.__tablename__ == "flash_authentication_sessions"
