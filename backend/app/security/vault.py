from cryptography.fernet import Fernet
from app.core.config import get_settings
import structlog

logger = structlog.get_logger()


def _get_fernet() -> Fernet:
    key = get_settings().credential_encryption_key
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(value: str) -> str:
    """Encrypt a plaintext string. Returns base64-encoded ciphertext."""
    if not value:
        return value
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt(encrypted: str) -> str:
    """Decrypt a Fernet-encrypted string. Returns plaintext."""
    if not encrypted:
        return encrypted
    return _get_fernet().decrypt(encrypted.encode()).decode()


def generate_key() -> str:
    """Generate a new Fernet key (use once, store as CREDENTIAL_ENCRYPTION_KEY)."""
    return Fernet.generate_key().decode()
