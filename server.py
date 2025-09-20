from concurrent import futures
import grpc
import uuid
import hashlib

import booking_pb2
import booking_pb2_grpc
import database as db

# This dictionary acts as a temporary session store
# Key: token, Value: {'username': username, 'role': role}
SESSIONS = {}

class TicketingService(booking_pb2_grpc.TicketingServicer):
    
    def Login(self, request, context):
        print(f"Login attempt for user: {request.username}")
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT hashed_password, role FROM users WHERE username=?", (request.username,))
        user_record = cursor.fetchone()
        conn.close()

        if user_record:
            stored_hashed_pass, role = user_record
            provided_pass_hash = hashlib.sha256(request.password.encode()).hexdigest()
            if stored_hashed_pass == provided_pass_hash:
                token = str(uuid.uuid4())
                SESSIONS[token] = {'username': request.username, 'role': role}
                print(f"Login successful for {request.username}. Role: {role}")
                return booking_pb2.LoginResponse(success=True, message=f"Welcome, {request.username}!", token=token, role=role)

        print(f"Login failed for user: {request.username}")
        return booking_pb2.LoginResponse(success=False, message="Invalid credentials")

    def AddTravelService(self, request, context):
        print(f"Attempt to add a new travel service...")
        
        # 1. Authenticate and Authorize the admin
        session_info = SESSIONS.get(request.admin_token)
        if not session_info or session_info['role'] != 'ADMIN':
            print("Failed: Unauthorized or invalid token.")
            return booking_pb2.StatusResponse(success=False, message="Unauthorized: Admin access required.")

        # 2. Prepare the service details for the database
        service_details = {
            'service_id': str(uuid.uuid4()),
            'type': booking_pb2.ServiceType.Name(request.type), # Converts enum number to string name
            'identifier': request.identifier,
            'origin': request.origin,
            'destination': request.destination,
            'date': request.date,
            'total_seats': request.total_seats
        }

        # 3. Store the service in the database
        try:
            db.add_service_to_db(service_details)
            print(f"Success: Service '{request.identifier}' added by admin '{session_info['username']}'.")
            return booking_pb2.StatusResponse(success=True, message="Service added successfully.")
        except Exception as e:
            print(f"Failed: Database error - {e}")
            return booking_pb2.StatusResponse(success=False, message=f"Database error: {e}")

    # --- TODO: Implement the customer functions next ---

def serve():
    db.init_db()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    booking_pb2_grpc.add_TicketingServicer_to_server(TicketingService(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    print("🚀 Server started on port 50051")
    server.wait_for_termination()

if __name__ == '__main__':
    serve()