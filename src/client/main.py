import grpc
import train_booking_pb2
import train_booking_pb2_grpc

def run():
    # Establish a connection to the gRPC server
    with grpc.insecure_channel('localhost:50051') as channel:
        stub = train_booking_pb2_grpc.TicketingStub(channel)
        admin_token = ""
        customer_token = ""
        service_id_to_book = ""

        print("--- 1. Admin Login ---")
        try:
            login_response = stub.Login(train_booking_pb2.LoginRequest(username='admin', password='admin123'))
            if not login_response.success:
                print(f"❌ Admin login failed: {login_response.message}")
                return
            admin_token = login_response.token
            print("✅ Admin login successful.")
        except grpc.RpcError as e:
            print(f"❌ RPC Error during admin login: {e.details()}")
            return

        print("\n--- 2. Admin Adds a New Train Route ---")
        try:
            add_train_req = train_booking_pb2.AddTrainRequest(
                admin_token=admin_token,
                train_number=12951,
                train_name="Mumbai Rajdhani",
                source_city_id=1,
                destination_city_id=2,
                train_type="Express"
            )
            response = stub.AddTrain(add_train_req)
            print(f"✅ Add Train Response: Success={response.success}, Message='{response.message}'")
        except grpc.RpcError as e:
            print(f"❌ RPC Error adding train: {e.details()}")
            return
            
        print("\n--- 3. Admin Adds a Specific Train Service ---")
        try:
            seat_info = [
                train_booking_pb2.SeatInfo(seat_type=train_booking_pb2.AC2, seats_available=50, price=2500.0),
                train_booking_pb2.SeatInfo(seat_type=train_booking_pb2.AC3, seats_available=100, price=1800.0)
            ]
            add_service_req = train_booking_pb2.AddTrainServiceRequest(
                admin_token=admin_token,
                train_number=12951,
                datetime_of_departure="2025-12-25 08:00:00",
                datetime_of_arrival="2025-12-26 12:00:00",
                seat_info=seat_info
            )
            response = stub.AddTrainService(add_service_req)
            print(f"✅ Add Service Response: Success={response.success}, Message='{response.message}'")
        except grpc.RpcError as e:
            print(f"❌ RPC Error adding service: {e.details()}")
            return

        print("\n--- 4. Customer Logs In ---")
        try:
            login_response = stub.Login(train_booking_pb2.LoginRequest(username='customer', password='cust123'))
            if not login_response.success:
                print(f"❌ Customer login failed: {login_response.message}")
                return
            customer_token = login_response.token
            print(f"✅ Customer login successful.")
        except grpc.RpcError as e:
            print(f"❌ RPC Error during customer login: {e.details()}")
            return

        print("\n--- 5. Customer Searches for the Service ---")
        try:
            search_request = train_booking_pb2.SearchRequest(
                source_city_id=1, # New Delhi
                destination_city_id=2, # Mumbai
                date="2025-12-25"
            )
            search_response = stub.SearchTrainServices(search_request)
            if not search_response.services:
                print("❌ No services found for the customer.")
                return
            
            service_to_book = search_response.services[0]
            service_id_to_book = service_to_book.service_id
            print(f"✅ Found service: {service_to_book.train_name} (ID: {service_id_to_book[:8]}...)")
        except grpc.RpcError as e:
            print(f"❌ RPC Error during search: {e.details()}")
            return

        print("\n--- 6. Customer Books a Seat ---")
        try:
            booking_request = train_booking_pb2.BookSeatsRequest(
                customer_token=customer_token,
                service_id=service_id_to_book,
                number_of_seats=2
            )
            confirmation = stub.BookSeats(booking_request)
            if confirmation.success:
                print(f"✅ Booking successful!")
                print(f"   Booking ID: {confirmation.booking_id}")
                print(f"   Total Cost: ₹{confirmation.total_cost:.2f}")
            else:
                print(f"❌ Booking failed: {confirmation.message}")
        except grpc.RpcError as e:
            print(f"❌ RPC Error during booking: {e.details()}")

if __name__ == '__main__':
    run()