import sqlite3
import time
import uuid

from .connection import get_db_connection 

def create_user(username, hashed_password):
    """
    Inserts a new customer into the Users table.
    Returns True on success, False on failure (e.g., username exists).
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO Users (username, hashed_password, role) VALUES (?, ?, 'CUSTOMER')",
            (username, hashed_password)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # This error occurs if the username is already taken
        return False
    finally:
        conn.close()

def get_user_by_username(username):
    """
    Retrieves a single user record by their username.
    Returns a dictionary-like Row object or None if not found.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    return user

def create_session(user_id, token, expires_at):
    """Creates a new session for a user."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO Sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, time.time(), expires_at)
    )
    conn.commit()
    conn.close()

def get_user_by_token(token):
    """
    Validates a session token and retrieves the associated user.
    Returns the user record if the token is valid and not expired, otherwise None.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Users.* FROM Users
        JOIN Sessions ON Users.user_id = Sessions.user_id
        WHERE Sessions.token = ? AND Sessions.expires_at > ?
    """, (token, time.time()))
    user = cursor.fetchone()
    conn.close()
    return user

def delete_session(token):
    """Deletes a session record, effectively logging the user out."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM Sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()
    
def get_all_cities():
    """Retrieves all cities from the Cities table."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT city_id, city_name, city_code FROM Cities")
    cities = cursor.fetchall()
    conn.close()
    return cities


def add_train(train_number, train_name, source_city_id, destination_city_id, train_type):
    """Adds a new train template using city IDs."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO Trains (train_number, train_name, source_city_id, destination_city_id, train_type) VALUES (?, ?, ?, ?, ?)",
            (train_number, train_name, source_city_id, destination_city_id, train_type)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()
        
def search_services(source_city_id, destination_city_id, date):
    """
    Searches for services using city IDs and joins with Cities to get names.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            ts.service_id, t.train_number, t.train_name,
            ts.datetime_of_departure, ts.datetime_of_arrival,
            ts.seat_type, ts.seats_available, ts.price,
            source_city.city_name as source_city_name,
            dest_city.city_name as destination_city_name
        FROM TrainServices ts
        JOIN Trains t ON ts.train_number = t.train_number
        JOIN Cities source_city ON t.source_city_id = source_city.city_id
        JOIN Cities dest_city ON t.destination_city_id = dest_city.city_id
        WHERE t.source_city_id = ? AND t.destination_city_id = ? AND date(ts.datetime_of_departure) = ?
    """, (source_city_id, destination_city_id, date))
    services = cursor.fetchall()
    conn.close()
    return services

def add_train_service(train_number, dt_departure, dt_arrival, seat_info):
    """Adds one or more specific, bookable services for a train."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        services_to_add = []
        for info in seat_info:
            services_to_add.append((
                str(uuid.uuid4()),
                train_number,
                dt_departure,
                dt_arrival,
                info['seat_type'],
                info['seats_available'],
                info['price']
            ))
        
        cursor.executemany("""
            INSERT INTO TrainServices 
            (service_id, train_number, datetime_of_departure, datetime_of_arrival, seat_type, seats_available, price)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, services_to_add)
        conn.commit()
        return True
    except Exception as e:
        print(f"Error adding train service: {e}")
        return False
    finally:
        conn.close()
        

def book_seats(user_id, service_id, num_seats):
    """
    Books a specified number of seats for a service in a single transaction.
    Returns (success, message, booking_id, total_cost).
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        
        cursor.execute("BEGIN")

        
        cursor.execute("SELECT seats_available, price FROM TrainServices WHERE service_id = ?", (service_id,))
        service = cursor.fetchone()

        if not service or service['seats_available'] < num_seats:
            conn.rollback()
            return False, "Not enough seats available.", None, None

    
        total_cost = service['price'] * num_seats
        
        new_seat_count = service['seats_available'] - num_seats
        cursor.execute("UPDATE TrainServices SET seats_available = ? WHERE service_id = ?", (new_seat_count, service_id))

        #TODO: include status and timestamp to insert into Bookings
        booking_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO Bookings (booking_id, user_id, service_id, number_of_seats, total_cost)
            VALUES (?, ?, ?, ?, ?)
        """, (booking_id, user_id, service_id, num_seats, total_cost))

        
        conn.commit()
        
        return True, "Booking successful.", booking_id, total_cost

    except Exception as e:
        conn.rollback()
        return False, f"An error occurred: {e}", None, None
    finally:
        conn.close()