import time
import grpc
import train_booking_pb2
import train_booking_pb2_grpc
from database import models as db_models
from utils import security as security_utils

# Session duration in seconds (e.g., 24 hours)
SESSION_DURATION_SECONDS = 24 * 60 * 60

class BookingService(train_booking_pb2_grpc.TicketingServicer):
    """Implements the gRPC service for the booking application."""

    def Register(self, request, context):
        print(f"Registration attempt for username: {request.username}")
        
        if not request.username or not request.password:
            return train_booking_pb2.StatusResponse(success=False, message="Username and password cannot be empty.")
            
        hashed_password = security_utils.hash_password(request.password)
        
        success = db_models.create_user(request.username, hashed_password)
        
        if success:
            return train_booking_pb2.StatusResponse(success=True, message="Registration successful.")
        else:
            return train_booking_pb2.StatusResponse(success=False, message="Username already exists.")

    def Login(self, request, context):
        print(f"Login attempt for user: {request.username}")

        user = db_models.get_user_by_username(request.username)
        
        if not user:
            return train_booking_pb2.LoginResponse(success=False, message="Invalid credentials.")

        if not security_utils.check_password(request.password, user['hashed_password']):
            return train_booking_pb2.LoginResponse(success=False, message="Invalid credentials.")
        
        token = security_utils.generate_token()
        expires_at = time.time() + SESSION_DURATION_SECONDS
        
        db_models.create_session(user['user_id'], token, expires_at)
        
        print(f"Login successful for {request.username}.")
        return train_booking_pb2.LoginResponse(success=True, message="Login successful.", token=token)
    
    def AddTrain(self, request, context):
        print(f"Request to add new train: {request.train_number}")
        
        admin_user = db_models.get_user_by_token(request.admin_token)
        if not admin_user or admin_user['role'] != 'ADMIN':
            return train_booking_pb2.StatusResponse(success=False, message="Unauthorized")
        
        success = db_models.add_train(
            request.train_number,
            request.train_name,
            request.source_city_id,
            request.destination_city_id,
            request.train_type
        )

        if success:
            return train_booking_pb2.StatusResponse(success=True, message="Train added successfully.")
        else:
            return train_booking_pb2.StatusResponse(success=False, message="Train number already exists.")

    def AddTrainService(self, request, context):
        print(f"Request to add new service for train: {request.train_number}")


        admin_user = db_models.get_user_by_token(request.admin_token)
        if not admin_user or admin_user['role'] != 'ADMIN':
            return train_booking_pb2.StatusResponse(success=False, message="Unauthorized")
        

        seat_info_list = [{
            'seat_type': train_booking_pb2.SeatType.Name(info.seat_type),
            'seats_available': info.seats_available,
            'price': info.price
        } for info in request.seat_info]
        
        success = db_models.add_train_service(
            request.train_number,
            request.datetime_of_departure,
            request.datetime_of_arrival,
            seat_info_list
        )

        if success:
            return train_booking_pb2.StatusResponse(success=True, message="Train services added successfully.")
        else:
            return train_booking_pb2.StatusResponse(success=False, message="Failed to add train services.")
    
    def SearchTrainServices(self, request, context):
        """
        Handles a customer's request to search for available train services.
        """
        
        print(f"Request to search for trains from city ID {request.source_city_id} to {request.destination_city_id} on {request.date}")
        
        try: 
            services_from_db = db_models.search_services(
                request.source_city_id,
                request.destination_city_id,
                request.date
            )
            
            response = train_booking_pb2.SearchResponse()
            
            for service_row in services_from_db:
                summary = response.services.add()
                summary.service_id = service_row['service_id']
                summary.train_number = service_row['train_number']
                summary.train_name = service_row['train_name']
                summary.datetime_of_departure = service_row['datetime_of_departure']
                summary.datetime_of_arrival = service_row['datetime_of_arrival']
                summary.seat_type = train_booking_pb2.SeatType.Value(service_row['seat_type'])
                summary.seats_available = service_row['seats_available']
                summary.price = service_row['price']
                
            print(f"Found {len(services_from_db)} matching services.")
            return response

        except Exception as e:
            print(f"An error occurred during search: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"An internal error occurred: {e}")
            return train_booking_pb2.SearchResponse()
    
    def BookSeats(self, request, context):
        print(f"Request to book {request.number_of_seats} seats for service {request.service_id}")
        
        user = db_models.get_user_by_token(request.customer_token)
        if not user or user['role'] != 'CUSTOMER':
            return train_booking_pb2.BookingConfirmation(success=False, message="Unauthorized")
        
        success, message, booking_id, total_cost = db_models.book_seats(
            user['user_id'],
            request.service_id,
            request.number_of_seats
        )
        
        return train_booking_pb2.BookingConfirmation(
            success=success,
            message=message,
            booking_id=booking_id or "",
            total_cost=total_cost or 0.0
        )
        
    def ListCities(self, request, context):
        print("Request to list all cities")
        cities_from_db = db_models.get_all_cities()
        response = train_booking_pb2.ListCitiesResponse()
        for city_row in cities_from_db:
            city_proto = response.cities.add()
            city_proto.city_id = city_row['city_id']
            city_proto.city_name = city_row['city_name']
            city_proto.city_code = city_row['city_code']
        return response