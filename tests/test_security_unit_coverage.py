import pytest

from tksessentials import security


def test_get_secret_key_returns_env_value(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "top-secret")
    assert security.get_secret_key() == "top-secret"


def test_get_secret_key_raises_when_missing(monkeypatch):
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    with pytest.raises(ValueError, match="ENCRYPTION_KEY"):
        security.get_secret_key()


def test_get_jwt_secret_returns_env_value(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "jwt-secret")
    assert security.get_JWT_secret() == "jwt-secret"


def test_get_jwt_secret_raises_when_missing(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValueError, match="JWT_SECRET"):
        security.get_JWT_secret()


def test_get_aes_secret_returns_bytes(monkeypatch):
    monkeypatch.setenv("AES_SECRET", "abc123")
    assert security.get_AES_secret() == b"abc123"


def test_get_aes_secret_raises_when_empty(monkeypatch):
    monkeypatch.setenv("AES_SECRET", "")
    with pytest.raises(ValueError, match="AES_SECRET"):
        security.get_AES_secret()


def test_get_secret_key_raises_when_empty(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "")
    with pytest.raises(ValueError, match="ENCRYPTION_KEY"):
        security.get_secret_key()


def test_get_jwt_secret_raises_when_empty(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "")
    with pytest.raises(ValueError, match="JWT_SECRET"):
        security.get_JWT_secret()


def test_crypto_encrypt_and_decrypt_supports_unicode(monkeypatch):
    monkeypatch.setenv("AES_SECRET", "ZufDdKmoYgBv272G0DQWqz8Ng9ewM+IMGIMzkRQUoVNujiCHfdD4EULwXtn5fvwL")
    cipher = security.Crypto()

    encrypted = cipher.encrypt_as_text("päylöäd🔒")
    assert isinstance(encrypted, str)
    assert cipher.decrypt_as_text(encrypted) == "päylöäd🔒"


def test_crypto_encrypt_as_text_rejects_non_string_payload(monkeypatch):
    monkeypatch.setenv("AES_SECRET", "ZufDdKmoYgBv272G0DQWqz8Ng9ewM+IMGIMzkRQUoVNujiCHfdD4EULwXtn5fvwL")
    cipher = security.Crypto()

    with pytest.raises(TypeError):
        cipher.encrypt(12)


def test_crypto_decrypt_as_text_rejects_malformed_payload(monkeypatch):
    monkeypatch.setenv("AES_SECRET", "ZufDdKmoYgBv272G0DQWqz8Ng9ewM+IMGIMzkRQUoVNujiCHfdD4EULwXtn5fvwL")
    cipher = security.Crypto()

    with pytest.raises(Exception):
        cipher.decrypt_as_text("not-a-valid-payload")
