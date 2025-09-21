import bcrypt
import secrets

def hash_password(password: str) -> bytes:
    """Hashes a plaintext password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

def check_password(password: str, hashed_password: bytes) -> bool:
    """Verifies a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password)

def generate_token() -> str:
    """Generates a secure, URL-safe token for sessions."""
    return secrets.token_urlsafe(32)