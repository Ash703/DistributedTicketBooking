import sqlite3
import bcrypt
import secrets
import time
from utils import config

# Database Initialization
def get_db_connection():
    """Establishes a connection to the database, enabling foreign key support."""
    conn = sqlite3.connect(config.DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON") 
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize users and sessions tables."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        hashed_password TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('ADMIN', 'CUSTOMER'))
    )
    """)

    # 2. Session Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL, -- The new column for the expiry timestamp
    FOREIGN KEY(user_id) REFERENCES Users(user_id) ON DELETE CASCADE
    )
    """)

    # 3. Train Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Trains (
        train_number INTEGER PRIMARY KEY,
        train_name TEXT NOT NULL,
        source_city_id INTEGER NOT NULL,
        destination_city_id INTEGER NOT NULL,
        train_type TEXT,
        FOREIGN KEY(source_city_id) REFERENCES Cities(city_id),
        FOREIGN KEY(destination_city_id) REFERENCES Cities(city_id)
    )
    """)

    # 4. TrainService Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS TrainServices (
    service_id TEXT PRIMARY KEY,
    train_number INTEGER NOT NULL,
    datetime_of_departure TEXT NOT NULL,
    datetime_of_arrival TEXT NOT NULL,
    seat_type TEXT NOT NULL CHECK(seat_type IN ('AC1', 'AC2', 'AC3', 'GENERAL')),
    seats_available INTEGER NOT NULL,
    price REAL NOT NULL,
    FOREIGN KEY(train_number) REFERENCES Trains(train_number) ON DELETE CASCADE
    )
    """)

    # 5. Booking Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Bookings (
    booking_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    service_id TEXT NOT NULL,
    number_of_seats INTEGER NOT NULL,
    total_cost REAL NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING', 'CONFIRMED', 'CANCELLED')),
    booking_timestamp REAL NOT NULL DEFAULT (strftime('%s', 'now')),
    FOREIGN KEY(user_id) REFERENCES Users(user_id), 
    FOREIGN KEY(service_id) REFERENCES TrainServices(service_id)
    )
    """)
    
    # 6. Payment Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Payments (
    payment_id TEXT PRIMARY KEY,
    booking_id TEXT NOT NULL,
    amount REAL NOT NULL,
    payment_mode TEXT,
    payment_status TEXT NOT NULL CHECK(payment_status IN ('PENDING', 'SUCCESS', 'FAILED')),
    transaction_id TEXT, -- The ID from the payment gateway
    payment_timestamp REAL NOT NULL DEFAULT (strftime('%s', 'now')),
    FOREIGN KEY(booking_id) REFERENCES Bookings(booking_id)
    )
    """)
    
    # 7. City Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Cities (
        city_id INTEGER PRIMARY KEY AUTOINCREMENT,
        city_name TEXT UNIQUE NOT NULL,
        city_code TEXT UNIQUE NOT NULL
    )
    """)

    #Default Users
    try:
        admin_pass = b'admin123'
        cust_pass = b'cust123'
        hashed_admin_pass = bcrypt.hashpw(admin_pass, bcrypt.gensalt())
        hashed_cust_pass = bcrypt.hashpw(cust_pass, bcrypt.gensalt())

        cursor.execute("INSERT OR IGNORE INTO Users (username, hashed_password, role) VALUES (?, ?, ?)",
                       ('admin', hashed_admin_pass, 'ADMIN'))
        cursor.execute("INSERT OR IGNORE INTO Users (username, hashed_password, role) VALUES (?, ?, ?)",
                       ('customer', hashed_cust_pass, 'CUSTOMER'))
    except sqlite3.IntegrityError:
        print("Default users already exist.")
    
    cities_to_add = [
        ('New Delhi', 'NDLS'),
        ('Mumbai Central', 'MMCT'),
        ('Jaipur', 'JP'),
        ('Chennai Central', 'MAS')
    ]
    cursor.executemany("INSERT OR IGNORE INTO Cities (city_name, city_code) VALUES (?, ?)", cities_to_add)

        
        
    conn.commit()
    conn.close()
    print("\nDatabase initialized successfully.")


if __name__ == '__main__':
    init_db()