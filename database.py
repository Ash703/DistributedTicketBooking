import sqlite3
import hashlib
import uuid

DB_NAME = 'ticketing.db'

def get_db_connection():
    """Establishes a connection to the database."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row # Allows accessing columns by name
    return conn

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create users table with a CHECK constraint for the role
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        hashed_password TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('ADMIN', 'CUSTOMER'))
    )
    ''')

    # Create travel_services table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS travel_services (
        service_id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        identifier TEXT NOT NULL,
        origin TEXT NOT NULL,
        destination TEXT NOT NULL,
        date TEXT NOT NULL,
        total_seats INTEGER NOT NULL,
        available_seats INTEGER NOT NULL
    )
    ''')

    # Create bookings table with FOREIGN KEY constraints for data integrity
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bookings (
        booking_id TEXT PRIMARY KEY,
        service_id TEXT NOT NULL,
        username TEXT NOT NULL,
        num_seats INTEGER NOT NULL,
        FOREIGN KEY(service_id) REFERENCES travel_services(service_id),
        FOREIGN KEY(username) REFERENCES users(username)
    )
    ''')

    # Add a default admin and customer user if they don't exist
    users_to_add = [
        ('admin', hashlib.sha256('admin123'.encode()).hexdigest(), 'ADMIN'),
        ('customer', hashlib.sha256('cust123'.encode()).hexdigest(), 'CUSTOMER')
    ]
    cursor.executemany("INSERT OR IGNORE INTO users (username, hashed_password, role) VALUES (?, ?, ?)", users_to_add)

    conn.commit()
    conn.close()
    print("Database initialized successfully.")

def add_service_to_db(service_details):
    """Adds a new travel service to the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO travel_services (service_id, type, identifier, origin, destination, date, total_seats, available_seats)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        service_details['service_id'],
        service_details['type'],
        service_details['identifier'],
        service_details['origin'],
        service_details['destination'],
        service_details['date'],
        service_details['total_seats'],
        service_details['total_seats'] # Initially, available_seats equals total_seats
    ))
    conn.commit()
    conn.close()

# When this script is run directly, it will create and set up the database.
if __name__ == '__main__':
    init_db()