import grpc
import generated.train_pb2 as train_pb2
import generated.train_pb2_grpc as train_pb2_grpc
import json

def run_client(server_address='localhost:50051'):
    """
    Connects to the gRPC server and runs a sequence of operations.
    """
    try:
        with grpc.insecure_channel(server_address) as channel:
            stub = train_pb2_grpc.BookingServiceStub(channel)
            print("--- Client Connected to Server ---")

            # --- 1. Admin Login and Add a New Train Service ---
            print("\n### Admin Actions ###")
            
            # Login as Admin (assuming user 'admin' with password 'password' exists)
            login_req = train_pb2.LoginRequest(username="admin", password="password")
            login_res = stub.Login(login_req)

            if not login_res.status:
                print("Admin login failed.")
                return

            admin_token = login_res.token
            print(f"Admin login successful. Token: {admin_token[:10]}...")

            # Add a new train service
            service_data = {
                "train_name": "Rajdhani Express",
                "train_number": "12302",
                "source": "New Delhi",
                "destination": "Howrah",
                "departure_time": "17:00",
                "arrival_time": "10:00",
                "available_seats": 100
            }
            
            post_req = train_pb2.PostRequest(
                token=admin_token,
                type="ADD_SERVICE",
                data=json.dumps(service_data)  # Serialize data to JSON string
            )
            
            post_res = stub.Post(post_req)
            if post_res.status:
                print(f"Successfully posted new service: {post_res.message}")
            else:
                print(f"Failed to post new service: {post_res.message}")
                return

            # --- 2. Customer Login and List Services ---
            print("\n### Customer Actions ###")
            
            # Login as a regular user (assuming user 'user1' with password 'pass1' exists)
            login_req_user = train_pb2.LoginRequest(username="user1", password="password123")
            login_res_user = stub.Login(login_req_user)

            if not login_res_user.status:
                print("User login failed.")
                return

            user_token = login_res_user.token
            print(f"User login successful. Token: {user_token[:10]}...")

            # Get the list of available services
            get_req = train_pb2.GetRequest(
                token=user_token,
                type="LIST_SERVICES",
                params={"source": "New Delhi", "destination": "Howrah"}
            )
            
            get_res = stub.Get(get_req)
            
            if get_res.status:
                print("\n--- Available Services ---")
                if not get_res.items:
                    print("No services found.")
                else:
                    for item in get_res.items:
                        service_details = json.loads(item.data)
                        print(f"  ID: {item.id}")
                        print(f"  Train: {service_details.get('train_name')} ({service_details.get('train_number')})")
                        print(f"  Route: {service_details.get('source')} -> {service_details.get('destination')}")
                        print(f"  Departure: {service_details.get('departure_time')}")
                        print(f"  Arrival: {service_details.get('arrival_time')}")
                        print(f"  Seats Available: {service_details.get('available_seats')}")
                        print("-" * 20)
            else:
                print("Failed to retrieve services.")

    except grpc.RpcError as e:
        print(f"An RPC error occurred: {e.code()} - {e.details()}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == '__main__':
    run_client()