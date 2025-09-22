import grpc
import train_booking_pb2
import train_booking_pb2_grpc

def run_full_flow():
    """Simulates the full workflow: admin setup, customer search, booking, and viewing bookings."""
    with grpc.insecure_channel('localhost:50051') as channel:
        stub = train_booking_pb2_grpc.TicketingStub(channel)
        print("✅ Client connected to server.")

        # --- ADMIN FLOW ---
        print("\n--- 1. Admin logs in and creates a service ---")
        try:
            admin_login_res = stub.Login(train_booking_pb2.LoginRequest(username='admin', password='admin123'))
            admin_token = admin_login_res.token
            print("✅ Admin logged in.")

            # Get City IDs to use in requests
            list_cities_resp = stub.ListCities(train_booking_pb2.ListCitiesRequest())
            city_map = {c.city_name: c.city_id for c in list_cities_resp.cities}
            delhi_id = city_map.get("New Delhi")
            mumbai_id = city_map.get("Mumbai Central")

            # Add Train route
            add_train_req = train_booking_pb2.AddTrainRequest(
                admin_token=admin_token, train_number=12951, train_name="Mumbai Rajdhani",
                source_city_id=delhi_id, destination_city_id=mumbai_id, train_type="Rajdhani"
            )
            stub.AddTrain(add_train_req)
            
            # Add a specific Service for that train
            seat_info = [train_booking_pb2.SeatInfo(seat_type=train_booking_pb2.AC2, seats_available=50, price=3500.0)]
            add_service_req = train_booking_pb2.AddTrainServiceRequest(
                admin_token=admin_token, train_number=12951,
                datetime_of_departure="2025-12-25 17:00:00",
                datetime_of_arrival="2025-12-26 09:00:00", seat_info=seat_info
            )
            stub.AddTrainService(add_service_req)
            print("✅ Admin data setup complete.")
        except grpc.RpcError as e:
            print(f"❌ Admin flow failed: {e.details()}")
            return

        # --- CUSTOMER FLOW ---
        print("\n--- 2. Customer searches for the service ---")
        search_request = train_booking_pb2.SearchRequest(source_city_id=delhi_id, destination_city_id=mumbai_id, date="2025-12-25")
        search_response = stub.SearchTrainServices(search_request)
        
        if not search_response.services:
            print("❌ Test failed: No services found for the customer.")
            return
        
        service_to_book = search_response.services[0]
        service_id_to_book = service_to_book.service_id
        print(f"✅ Search successful. Found '{service_to_book.train_name}' with ID {service_id_to_book[:8]}...")
        
        print("\n--- 3. Customer logs in ---")
        customer_login_res = stub.Login(train_booking_pb2.LoginRequest(username='customer', password='cust123'))
        customer_token = customer_login_res.token
        print("✅ Customer login successful.")

        print("\n--- 4. Customer initiates booking (reserves seats) ---")
        init_req = train_booking_pb2.InitiateBookingRequest(
            customer_token=customer_token, service_id=service_id_to_book, number_of_seats=2
        )
        booking_confirmation = stub.InitiateBooking(init_req)
        
        if not booking_confirmation.success:
            print(f"❌ Booking initiation failed: {booking_confirmation.message}")
            return
        
        booking_id = booking_confirmation.booking_id
        print(f"✅ Seats reserved! Booking ID: {booking_id[:8]}..., Total Cost: {booking_confirmation.total_cost}")

        print("\n--- 5. Customer processes payment ---")
        payment_req = train_booking_pb2.ProcessPaymentRequest(
            customer_token=customer_token, booking_id=booking_id, payment_mode="MockCreditCard"
        )
        payment_response = stub.ProcessPayment(payment_req)
        
        if not payment_response.success:
            print(f"❌ Payment failed: {payment_response.message}")
            return
        print(f"✅ Payment successful! Server says: '{payment_response.message}'")

        print("\n--- 6. Customer Views Their Bookings ---")
        try:
            my_bookings_req = train_booking_pb2.GetMyBookingsRequest(customer_token=customer_token)
            my_bookings_resp = stub.GetMyBookings(my_bookings_req)

            print(f"✅ Found {len(my_bookings_resp.bookings)} booking(s) for this user:")
            for booking in my_bookings_resp.bookings:
                print(f"  - Booking ID: {booking.booking_id[:8]}... | "
                      f"Train: {booking.train_name} | "
                      f"From: {booking.source} To: {booking.destination} | "
                      f"Date: {booking.datetime_of_departure}")

        except grpc.RpcError as e:
            print(f"❌ RPC Error while getting bookings: {e.details()}")

if __name__ == '__main__':
    run_full_flow()