import sqlite3
import bcrypt
import secrets
import time

DB_PATH = "train_booking.db"

# Database Initialization
def get_db():
    """Connect to SQLite database."""
    return sqlite3.connect(DB_PATH)

def init_db():
    """Initialize users and sessions tables."""
    conn = get_db()
    cur = conn.cursor()

    # Users table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash BLOB NOT NULL
    )
    ''')

    # Sessions table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER,
        created_at REAL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    ''')

    conn.commit()
    conn.close()
    print("Database initialized successfully.")

# Password Utilities
def hash_password(password: str) -> bytes:
    """Hash password with bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode(), salt)
    return hashed

def check_password(password: str, hashed: bytes) -> bool:
    """Verify password against hashed value."""
    return bcrypt.checkpw(password.encode(), hashed)

# User Management
def register_user(username: str, password: str) -> bool:
    """Register a new user."""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, hash_password(password))
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Username already exists
        return False
    finally:
        conn.close()

def authenticate(username: str, password: str) -> str | None:
    """
    Authenticate user credentials.
    Returns session token if successful, None otherwise.
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()

    if row and check_password(password, row[1]):
        user_id = row[0]
        token = secrets.token_hex(16)
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
            (token, user_id, time.time())
        )
        conn.commit()
        conn.close()
        return token

    return None

# Session Management
def verify_token(token: str) -> int | None:
    """Check if a session token is valid. Returns user_id if valid."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM sessions WHERE token = ?", (token,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def logout(token: str) -> bool:
    """Invalidate a session token (logout)."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    changes = cur.rowcount
    conn.close()
    return changes > 0

if __name__ == "__main__":
    init_db()

    # Register user
    if register_user("alice", "password123"):
        print("User registered successfully!")
    else:
        print("Username already exists!")

    # Authenticate
    token = authenticate("alice", "password123")
    if token:
        print("Login successful! Session token:", token)

        # Verify token
        user_id = verify_token(token)
        print("Token belongs to user ID:", user_id)

        # Logout
        if logout(token):
            print("Logged out successfully.")
    else:
        print("Invalid credentials.")