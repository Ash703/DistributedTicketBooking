import grpc
import booking_pb2
import booking_pb2_grpc

def run_admin_flow(stub):
    """Simulates an admin logging in and adding a new service."""
    print("--- 1. Admin Login ---")
    
    # Step 1: Log in as the admin user
    try:
        login_response = stub.Login(booking_pb2.LoginRequest(username='admin', password='admin123'))
        if not login_response.success:
            print(f"❌ Admin login failed: {login_response.message}")
            return
        
        admin_token = login_response.token
        print(f"✅ Admin login successful. Received token.")
    except grpc.RpcError as e:
        print(f"❌ RPC Error during login: {e.details()}")
        return

    print("\n--- 2. Add New Travel Service ---")
    
    # Step 2: Use the token to add a new flight service
    try:
        add_service_request = booking_pb2.AddServiceRequest(
            admin_token=admin_token,
            type=booking_pb2.FLIGHT,  # Using the enum for FLIGHT
            identifier="AI-202",
            origin="Delhi",
            destination="Mumbai",
            date="2025-10-15",
            total_seats=150
        )
        
        status_response = stub.AddTravelService(add_service_request)
        
        if status_response.success:
            print(f"✅ Success! Server says: '{status_response.message}'")
        else:
            print(f"❌ Failure! Server says: '{status_response.message}'")

    except grpc.RpcError as e:
        print(f"❌ RPC Error while adding service: {e.details()}")

def main():
    """Connects to the server and runs the test."""
    with grpc.insecure_channel('localhost:50051') as channel:
        stub = booking_pb2_grpc.TicketingStub(channel)
        run_admin_flow(stub)

if __name__ == '__main__':
    main()