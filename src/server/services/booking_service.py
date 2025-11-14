import asyncio
import grpc
import train_booking_pb2
import train_booking_pb2_grpc
import time
import json
import uuid
from database import models as db_models
from utils import security as security_utils
from utils import config
from openai import OpenAI

class BookingService(train_booking_pb2_grpc.TicketingServicer):

    def __init__(self, raft_node):
        self.raft = raft_node
        try:
            self.client = OpenAI(
            base_url="http://127.0.0.1:54922",  #Local LLM model URL, needs to be updated depending on the current port number
            api_key="not-needed"
            )
        except:
            print("ChatBot is not available.")
            pass

    async def Register(self, request, context):
        print(f"Registration attempt for username: {request.username}")
        
        if not request.username or not request.password:
            return train_booking_pb2.StatusResponse(success=False, message="Username and password cannot be empty.")
        
        if self.raft.state != "leader":
            leader = self.raft.leader_id or "unknown"
            return train_booking_pb2.StatusResponse(
                success=False,
                message=f"This node is not the leader. Please contact leader {leader}."
            )
            
        hashed_password = security_utils.hash_password(request.password)

        command_data = {
            "action": "REGISTER",
            "username": request.username,
            "hashed_password": hashed_password.decode('utf-8'),
            "role": "CUSTOMER"
        }
        command = json.dumps(command_data)

        raft_success, raft_msg = await self.raft.handle_client_command(command)

        if not raft_success:
            return train_booking_pb2.StatusResponse(success=False, message=raft_msg)

        return train_booking_pb2.StatusResponse(success=True, message="Registration successful.")

    async def Login(self, request, context):
        print(f"Login attempt for user: {request.username}")

        if self.raft.state != "leader":
            leader = self.raft.leader_id or "unknown"
            return train_booking_pb2.LoginResponse(
                success=False,
                message=f"This node is not the leader. Please contact leader {leader}."
            )
        user = await db_models.get_user_by_username(request.username)
        
        if not user:
            return train_booking_pb2.LoginResponse(success=False, message="Invalid credentials.")

        if not security_utils.check_password(request.password, user['hashed_password']):
            return train_booking_pb2.LoginResponse(success=False, message="Invalid credentials.")
        
        token = security_utils.generate_token()
        expires_at = time.time() + config.SESSION_DURATION_SECONDS
        
        command_data = {
            "action": "CREATE_SESSION",
            "user_id": user['user_id'],
            "token": token,
            "expires_at": expires_at
        }
        command = json.dumps(command_data)
        
        raft_success, raft_msg = await self.raft.handle_client_command(command)
        
        if not raft_success:
            return train_booking_pb2.LoginResponse(success=False, message=raft_msg)

        print(f"Login successful for {request.username}.")
        return train_booking_pb2.LoginResponse(success=True, message="Login successful.", token=token)
    
    async def AddTrain(self, request, context):
        print(f"Request to add new train: {request.train_number}")

        if self.raft.state != "leader":
            leader = self.raft.leader_id or "unknown"
            return train_booking_pb2.StatusResponse(
                success=False,
                message=f"This node is not the leader. Please contact leader {leader}."
            )
        
        admin_user = await db_models.get_user_by_token(request.admin_token)
        if not admin_user or admin_user['role'] != 'ADMIN':
            return train_booking_pb2.StatusResponse(success=False, message="Unauthorized")
        
        command_data = {
            "action": "ADD_TRAIN",
            "train_number": request.train_number,
            "train_name": request.train_name,
            "source_city_id": request.source_city_id,
            "destination_city_id": request.destination_city_id,
            "train_type": request.train_type
        }
        command = json.dumps(command_data)
        
        raft_success, raft_msg = await self.raft.handle_client_command(command)

        if not raft_success:
            return train_booking_pb2.StatusResponse(success=False, message=raft_msg)

        return train_booking_pb2.StatusResponse(success=True, message="Train added successfully.")

    async def AddTrainService(self, request, context):
        print(f"Request to add new service for train: {request.train_number}")

        admin_user = await db_models.get_user_by_token(request.admin_token)
        if not admin_user or admin_user['role'] != 'ADMIN':
            return train_booking_pb2.StatusResponse(success=False, message="Unauthorized")
        
        if self.raft.state != "leader":
            leader = self.raft.leader_id or "unknown"
            return train_booking_pb2.StatusResponse(
                success=False,
                message=f"This node is not the leader. Please contact leader {leader}."
            )

        seat_info_list = [{
            "service_id": str(uuid.uuid4()),
            'seat_type': train_booking_pb2.SeatType.Name(info.seat_type),
            'seats_available': info.seats_available,
            'price': info.price
        } for info in request.seat_info]
        
        command_data = {
            "action": "ADD_SERVICE",
            "train_number": request.train_number,
            "datetime_of_departure": request.datetime_of_departure,
            "datetime_of_arrival": request.datetime_of_arrival,
            "seat_info": seat_info_list 
        }
        command = json.dumps(command_data)
        
        raft_success, raft_msg = await self.raft.handle_client_command(command)

        if not raft_success:
            return train_booking_pb2.StatusResponse(success=False, message=raft_msg)

        return train_booking_pb2.StatusResponse(success=True, message="Train services added successfully.")
    
    async def SearchTrainServices(self, request, context):
        print(f"Request to search for trains from city ID {request.source_city_id} to {request.destination_city_id} on {request.date}")
        
        try: 
            services_from_db = await db_models.search_services(
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
                summary.source_city_name = service_row['source_city_name']
                summary.destination_city_name = service_row['destination_city_name']
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
    
    async def InitiateBooking(self, request, context):
        print(f"Request to initiate booking for {request.number_of_seats} seats on service {request.service_id}")

        if self.raft.state != "leader":
            leader = self.raft.leader_id or "unknown"
            return train_booking_pb2.BookingConfirmation(
                success=False,
                message=f"This node is not the leader. Please contact leader {leader}."
            )
        
        user = await db_models.get_user_by_token(request.customer_token)
        if not user or user['role'] != 'CUSTOMER':
            return train_booking_pb2.BookingConfirmation(success=False, message="Unauthorized")
        service = await db_models.get_service_price(request.service_id)
        
        if not service:
            return train_booking_pb2.BookingConfirmation(success=False, message="Service not found.")
        
        if service['seats_available'] < request.number_of_seats:
            return train_booking_pb2.BookingConfirmation(success=False, message="Not enough seats available.")
        booking_id = str(uuid.uuid4())
        total_cost = float(service['price']) * request.number_of_seats
        command_data = {
            "action": "BOOK_SEATS",
            "user_id": user['user_id'],
            "service_id": request.service_id,
            "number_of_seats": request.number_of_seats,
            "booking_id": booking_id, 
            "total_cost": total_cost  
        }
        command = json.dumps(command_data)
        
        raft_success, raft_msg = await self.raft.handle_client_command(command)

        if not raft_success:
            return train_booking_pb2.BookingConfirmation(success=False, message=raft_msg, booking_id="", total_cost=0.0)
        
        return train_booking_pb2.BookingConfirmation(
            success=True,
            message="Booking initiated. Please pay.",
            booking_id=booking_id,
            total_cost=total_cost
        )

    async def ProcessPayment(self, request, context):
        print(f"Request to process payment for booking_id: {request.booking_id}")
        
        user = await db_models.get_user_by_token(request.customer_token)
        if not user or user['role'] != 'CUSTOMER':
            return train_booking_pb2.StatusResponse(success=False, message="Unauthorized")
        
        if self.raft.state != "leader":
            leader = self.raft.leader_id or "unknown"
            return train_booking_pb2.StatusResponse(
                success=False,
                message=f"This node is not the leader. Please contact leader {leader}."
            )
        
        
        command_data = {
            "action": "CONFIRM_PAYMENT",
            "booking_id": request.booking_id,
            "payment_mode": request.payment_mode,
            "payment_id": str(uuid.uuid4()),
            "transaction_id": f"txn_{uuid.uuid4()}"
        }
        command = json.dumps(command_data)
        
        raft_success, raft_msg = await self.raft.handle_client_command(command)

        if not raft_success:
            return train_booking_pb2.StatusResponse(success=False, message=raft_msg)

        return train_booking_pb2.StatusResponse(success=True, message="Payment processed successfully.")
    
    async def GetMyBookings(self, request, context):
        print(f"Request to get bookings for token {request.customer_token[:8]}...")

        user = await db_models.get_user_by_token(request.customer_token)
        if not user:
            context.set_code(grpc.StatusCode.UNAUTHENTICATED)
            context.set_details("Invalid or expired token.")
            return train_booking_pb2.BookingList()

        user_bookings = await db_models.get_bookings_by_user_id(user['user_id'])
        
        response = train_booking_pb2.BookingList()
        for row in user_bookings:
            booking_details = response.bookings.add()
            booking_details.booking_id = row['booking_id']
            booking_details.train_name = row['train_name']
            booking_details.source = row['source'] 
            booking_details.destination = row['destination']
            booking_details.datetime_of_departure = row['datetime_of_departure']
            booking_details.number_of_seats = row['number_of_seats']
            booking_details.total_cost = row['total_cost']
            booking_details.seat_type = train_booking_pb2.SeatType.Value(row['seat_type'])
            booking_details.status = row['status']

        print(f"Found {len(user_bookings)} bookings for user '{user['username']}'.")
        return response

    async def ListCities(self, request, context):
        print("Request to list all cities")
        cities_from_db = await db_models.get_all_cities()
        response = train_booking_pb2.ListCitiesResponse()
        for city_row in cities_from_db:
            city_proto = response.cities.add()
            city_proto.city_id = city_row['city_id']
            city_proto.city_name = city_row['city_name']
            city_proto.city_code = city_row['city_code']
        return response
    
    async def GetAllTrains(self, request, context):
        print(f"Admin Request: List trains (Source: {request.source_city_id}, Dest: {request.destination_city_id})")
        user = await db_models.get_user_by_token(request.admin_token)
        if not user or user['role'] != 'ADMIN':
            context.set_code(grpc.StatusCode.PERMISSION_DENIED)
            context.set_details("Unauthorized: Admin access required.")
            return train_booking_pb2.GetAllTrainsResponse()
        try:
            trains_db = await db_models.get_trains_admin(request.source_city_id, request.destination_city_id)
        except Exception as e:
            print(f"Error fetching trains from DB: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Database error: {e}")
            return train_booking_pb2.GetAllTrainsResponse()
        response = train_booking_pb2.GetAllTrainsResponse()
        for row in trains_db:
            t = response.trains.add()
            t.train_number = row['train_number']
            t.train_name = row['train_name']
            t.train_type = row['train_type']
            t.source_city = row['source_name']
            t.destination_city = row['dest_name']
            
        print(f"Found {len(trains_db)} trains matching filter.")
        return response
    
    async def CancelBooking(self, request, context):
        print(f"Request to cancel booking: {request.booking_id}")

        if self.raft.state != "leader":
            leader = self.raft.leader_id or "unknown"
            return train_booking_pb2.StatusResponse(
                success=False,
                message=f"This node is not the leader. Please contact leader {leader}."
            )

        user = await db_models.get_user_by_token(request.customer_token)
        if not user:
            return train_booking_pb2.StatusResponse(success=False, message="Unauthorized")

        command_data = {
            "action": "CANCEL_BOOKING",
            "booking_id": request.booking_id,
            "user_id": user['user_id'] 
        }
        command = json.dumps(command_data)

        raft_success, raft_msg = await self.raft.handle_client_command(command)

        if not raft_success:
            return train_booking_pb2.StatusResponse(success=False, message=raft_msg)

        return train_booking_pb2.StatusResponse(success=True, message="Booking cancelled successfully.")
    
    async def AskBot(self, request, context):
        print(f"Chatbot query: {request.query}")
        user = await db_models.get_user_by_token(request.customer_token)
        if not user:
            context.set_code(grpc.StatusCode.UNAUTHENTICATED)
            context.set_details("Invalid or expired token.")
            yield train_booking_pb2.LLMAnswer(answer="Please log in.")
            return
        user_bookings = await db_models.get_bookings_by_user_id(user['user_id'])
        all_trains = await db_models.get_all_train_services_for_context()

        context_text = "USER BOOKINGS:\n"
        if not user_bookings:
            context_text += "The user currently has no confirmed bookings.\n"
        else:
            for booking in user_bookings:
                context_text += (
                    f"- Booking ID {booking['booking_id'][:8]} for '{booking['train_name']}' "
                    f"from '{booking['source']}' to '{booking['destination']}'. No. of seats '{booking['number_of_seats']}' of seat type: {booking['seat_type']}. "
                    f"on {booking['datetime_of_departure']}. Status: {booking['status']}.\n"
                )
        
        context_text += "\nAVAILABLE TRAIN CATALOG:\n"
        if all_trains:
            for t in all_trains:
                context_text += (
                    f"- Train '{t['train_name']}' from '{t['source']}' to '{t['destination']}' "
                    f"departs {t['datetime_of_departure']}. ({t['seat_type']}), ({t['price']}), ({t['seats_available']} seats left).\n"
                )

        
        system_prompt = (
            f"You are a helpful train booking assistant for user named {user['username']}. Greet them at start of every message.\n"
            f"Each train has multiple different seating class, such as AC!, AC2, AC3 and General. Each train's all seating classes must be listed under it. For a given train on a given day, each of these seating class must be listed under that along with price and seat available for each class.\n"
            f"You MUST ONLY answer questions related to train bookings or schedules based on the context below.\n"
            f"If the user asks about ANYTHING else (weather, politics, etc), politely refuse.\n\n"
            f"CONTEXT DATA:\n{context_text}"
        )
        try:
            stream = self.client.chat.completions.create(
                model="mistral",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": request.query}
                ],
                stream=True,
                temperature=0.3,
            )
            
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield train_booking_pb2.LLMAnswer(answer=delta.content)
            
        except Exception as e:
            print(f"LLM Error: {e}")
            yield train_booking_pb2.LLMAnswer(answer="Sorry, I am currently offline or having trouble answering.")