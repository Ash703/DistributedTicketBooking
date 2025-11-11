import grpc
import train_booking_pb2
import train_booking_pb2_grpc

# --- Leader Discovery Support ---
NODES = ["localhost:50051", "localhost:50052", "localhost:50053"]
current_node = NODES[0]

def get_stub(address):
    """Creates a stub for a given node address."""
    channel = grpc.insecure_channel(address)
    return train_booking_pb2_grpc.TicketingStub(channel), channel

def detect_and_redirect_if_not_leader(response_message):
    """
    Detects 'not leader' message and updates current_node accordingly.
    Expected message format:
      'This node is not the leader. Please contact leader 50052.'
    """
    global current_node
    if "not the leader" in response_message.lower():
        import re
        print(response_message)
        match = re.search(r"leader\s+(\d+)", response_message)
        if match:
            leader_id = match.group(1)
            new_node = NODES[int(leader_id)-1]
            if new_node != current_node:
                print(f"\nRedirecting to leader node at {new_node}...\n")
                current_node = new_node
                return True
    return False

def call_with_leader_redirect(rpc_name, request, max_retries=3):
    """
    Calls a gRPC RPC with automatic leader redirection and node failover.
    Retries across nodes if the current node is unavailable or not the leader.
    Always returns an object (either real response or dict with 'success' and 'message').
    """
    global current_node
    attempt = 0
    tried_nodes = set()

    while attempt < max_retries:
        stub, channel = get_stub(current_node)
        try:

            rpc_method = getattr(stub, rpc_name)
            resp = rpc_method(request)

            # --- Handle leader redirection ---
            if hasattr(resp, "message") and "not the leader" in resp.message.lower():
                if detect_and_redirect_if_not_leader(resp.message):
                    channel.close()
                    continue

            return resp

        except grpc.RpcError as e:
            code = e.code()
            details = e.details() or ""
            print(f"RPC Error from {current_node}: {details or code.name}")

            # --- Handle connectivity errors ---
            if code in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
                tried_nodes.add(current_node)
                next_candidates = [n for n in NODES if n not in tried_nodes]
                if not next_candidates:
                    print("All nodes unreachable. Cluster may be down.")
                    break
                current_node = next_candidates[0]
                print(f"Retrying on next node: {current_node}")
                attempt += 1
                continue
            else:
                break  # Non-retryable error

        finally:
            channel.close()

    class FallbackResponse:
        def __init__(self):
            self.success = False
            self.message = "All nodes unreachable or request failed."

    return FallbackResponse()

# --- Helper Functions for UI ---

def print_header(title):
    """Prints a clean, formatted header."""
    print("\n" + "=" * 50)
    print(f"| {title.upper():^46} |")
    print("=" * 50)

def print_main_menu(role):
    """Prints the main menu based on the user's role."""
    print_header("Main Menu")
    if role is None:
        print("1. Login")
        print("2. Register as a new customer")
        print("3. List all cities")
        print("4. Search for trains")
        print("5. Quit")
    elif role == "CUSTOMER":
        print("1. Search and book a train")
        print("2. View my bookings")
        print("3. Ask the chatbot")
        print("4. Logout")
    elif role == "ADMIN":
        print("1. Add a new train route")
        print("2. Add a new train service (schedule)")
        print("3. Logout")

def get_input(prompt, required=True):
    """Gets user input, handling empty required fields."""
    while True:
        val = input(f"> {prompt}: ").strip()
        if val or not required:
            return val
        print("  This field is required. Please try again.")

def get_int_input(prompt):
    """Gets and validates integer input."""
    while True:
        val = get_input(prompt)
        try:
            return int(val)
        except ValueError:
            print("  Invalid input. Please enter a number.")

def get_seat_type():
    """Helper to select a seat type enum."""
    print("  Select seat type:")
    print("  1: AC1")
    print("  2: AC2")
    print("  3: AC3")
    print("  4: GENERAL")
    while True:
        choice = get_input("  Choice")
        if choice == '1': return train_booking_pb2.AC1
        if choice == '2': return train_booking_pb2.AC2
        if choice == '3': return train_booking_pb2.AC3
        if choice == '4': return train_booking_pb2.GENERAL
        print("  Invalid choice. Please enter 1-4.")

# --- gRPC Action Functions ---

def do_login(stub):
    """Handles the login process."""
    print_header("Login")
    username = get_input("Username")
    password = get_input("Password")
    
    try:
        req = train_booking_pb2.LoginRequest(username=username, password=password)
        resp = call_with_leader_redirect("Login", req)
        
        if resp.success:
            print(f"\nLogin successful. {resp.message}")
            # We need to find the role from the database.
            # The LoginResponse should ideally return the role.
            # For this client, we'll manually check the 'admin' username.
            role = "ADMIN" if "admin" in username else "CUSTOMER"
            return resp.token, role
        else:
            print(f"\nLogin failed: {resp.message}")
            return None, None
    except grpc.RpcError as e:
        print(f"\nRPC Error: {e.details()}")
        return None, None

def do_register(stub):
    """Handles the new customer registration process."""
    print_header("Register New Customer")
    username = get_input("New Username")
    password = get_input("New Password")
    
    try:
        req = train_booking_pb2.RegisterRequest(username=username, password=password)
        resp = call_with_leader_redirect("Register", req)
        print(f"\n{resp.message}")
    except grpc.RpcError as e:
        print(f"\nRPC Error: {e.details()}")

def do_logout(stub, token):
    """Handles logging out."""
    try:
        stub.Logout(train_booking_pb2.LogoutRequest(token=token))
    except grpc.RpcError as e:
        # Logout is best-effort, so we don't need to over-handle errors
        pass
    print("\nYou have been logged out.")
    return None, None

def do_list_cities(stub):
    """Fetches and prints all cities."""
    print_header("Available Cities")
    try:
        req = train_booking_pb2.ListCitiesRequest()
        resp = stub.ListCities(req)
        
        if not resp.cities:
            print("No cities found in the system.")
            return None
        
        print(f"{'ID':<5} | {'Code':<8} | {'Name':<20}")
        print("-" * 37)
        for city in resp.cities:
            print(f"{city.city_id:<5} | {city.city_code:<8} | {city.city_name:<20}")
        return resp.cities
    except grpc.RpcError as e:
        print(f"\nRPC Error: {e.details()}")
        return None

def do_search_services(stub):
    """Handles searching for train services."""
    print_header("Search for Trains")
    
    if not do_list_cities(stub):
        print("\nCannot search without cities in the system.")
        return None
    
    print("\nEnter search details:")
    source_id = get_int_input("Source City ID")
    dest_id = get_int_input("Destination City ID")
    date = get_input("Date (YYYY-MM-DD)")
    
    try:
        req = train_booking_pb2.SearchRequest(
            source_city_id=source_id,
            destination_city_id=dest_id,
            date=date
        )
        resp = stub.SearchTrainServices(req)
        
        if not resp.services:
            print("\nNo services found matching your criteria.")
            return None
            
        print("\n--- Search Results ---")
        print(f"{'Service ID':<10} | {'Train':<17} | {'Departs':<20} | {'Arrives':<20} | {'Class':<8} | {'Seats':<5} | {'Price':<8}")
        print("-" * 92)
        
        for i, service in enumerate(resp.services):
            print(f"[{i+1}] {service.service_id[:8]:<7} | "
                  f"{service.train_name[:17]:<17} | "
                  f"{service.datetime_of_departure:<20} | "
                  f"{service.datetime_of_arrival:<20} | "
                  f"{train_booking_pb2.SeatType.Name(service.seat_type):<8} | "
                  f"{service.seats_available:<5} | "
                  f"{service.price:<8.2f}")
        return resp.services
        
    except grpc.RpcError as e:
        print(f"\nRPC Error: {e.details()}")
        return None

def do_search_and_book(stub, token):
    """Customer flow: search for trains and then optionally book one."""
    services = do_search_services(stub)
    
    if not services:
        return

    try:
        choice = get_int_input("\nEnter the number of the service to book (0 to cancel)")
        if choice == 0 or choice > len(services):
            print("Booking cancelled.")
            return
            
        service_to_book = services[choice - 1]
        
        num_seats = get_int_input(f"How many seats to book in {train_booking_pb2.SeatType.Name(service_to_book.seat_type)}?")
        if num_seats <= 0:
            print("Invalid number of seats. Cancelling.")
            return

        print_header("Initiating Booking")
        print(f"Booking {num_seats} seat(s) on {service_to_book.train_name}...")
        
        init_req = train_booking_pb2.InitiateBookingRequest(
            customer_token=token,
            service_id=service_to_book.service_id,
            number_of_seats=num_seats
        )
        init_resp = call_with_leader_redirect("InitiateBooking", init_req)
        
        if not init_resp.success:
            print(f"\nBooking Failed: {init_resp.message}")
            return
            
        print(f"\nBooking initiated! Total cost: {init_resp.total_cost:.2f}")
        print(f"Booking ID: {init_resp.booking_id}")
        
        confirm = get_input("Enter 'pay' to confirm payment (anything else to cancel)", required=False)
        if confirm.lower() != 'pay':
            print("Payment cancelled. Booking was not confirmed.")
            # We should call a 'CancelBooking' RPC here if we had one.
            return
            
        print("Processing payment...")
        pay_req = train_booking_pb2.ProcessPaymentRequest(
            customer_token=token,
            booking_id=init_resp.booking_id,
            payment_mode="CommandLinePay"
        )
        pay_resp = call_with_leader_redirect("ProcessPayment", pay_req)
        
        print(f"\n{pay_resp.message}")
        
    except grpc.RpcError as e:
        print(f"\nRPC Error: {e.details()}")

def do_view_bookings(stub, token):
    """Fetches and displays all bookings for the logged-in customer."""
    print_header("My Bookings")
    try:
        req = train_booking_pb2.GetMyBookingsRequest(customer_token=token)
        resp = stub.GetMyBookings(req)
        
        if not resp.bookings:
            print("You have no bookings.")
            return
            
        print(f"{'Booking ID':<10} | {'Train':<17} | {'From':<15} | {'To':<15} | {'Date':<20} | {'Seats':<5} | {'Status':<10}")
        print("-" * 98)
        
        for b in resp.bookings:
            print(f"{b.booking_id[:8]:<10} | "
                  f"{b.train_name[:17]:<17} | "
                  f"{b.source[:15]:<15} | "
                  f"{b.destination[:15]:<15} | "
                  f"{b.datetime_of_departure:<20} | "
                  f"{b.number_of_seats:<5} | "
                  f"{b.status:<10}")
                  
    except grpc.RpcError as e:
        print(f"\nRPC Error: {e.details()}")

def do_ask_bot(stub, token):
    """Starts an interactive session with the chatbot."""
    print_header("Chatbot")
    print("Type your questions. Type 'quit' or 'q' to exit.")
    
    while True:
        query = get_input("You")
        if query.lower() in ('q', 'quit'):
            break
            
        req = train_booking_pb2.LLMQuery(customer_token=token, query=query)
        
        try:
            print("\nBot:", end=" ", flush=True)
            for chunk in stub.AskBot(req):
                print(chunk.answer, end="", flush=True)
            print("\n")
        except grpc.RpcError as e:
            print(f"\nRPC Error: {e.details()}")
            break

def do_add_train(stub, token):
    """Admin function to add a new train route."""
    print_header("Add New Train Route")
    if not do_list_cities(stub):
        print("\nCannot add a train without cities in the system.")
        return
        
    train_number = get_int_input("Train Number (e.g., 12951)")
    train_name = get_input("Train Name (e.g., Mumbai Rajdhani)")
    source_id = get_int_input("Source City ID")
    dest_id = get_int_input("Destination City ID")
    train_type = get_input("Train Type (e.g., Rajdhani)")
    
    req = train_booking_pb2.AddTrainRequest(
        admin_token=token,
        train_number=train_number,
        train_name=train_name,
        source_city_id=source_id,
        destination_city_id=dest_id,
        train_type=train_type
    )
    
    try:
        resp = call_with_leader_redirect("AddTrain",req)
        print(f"\n{resp.message}")
    except grpc.RpcError as e:
        print(f"\nRPC Error: {e.details()}")

def do_add_service(stub, token):
    """Admin function to schedule a service for an existing train."""
    print_header("Add New Train Service (Schedule)")
    
    train_number = get_int_input("Train Number to schedule")
    dt_departure = get_input("Departure Datetime (YYYY-MM-DD HH:MM:SS)")
    dt_arrival = get_input("Arrival Datetime (YYYY-MM-DD HH:MM:SS)")
    
    seat_info_list = []
    while True:
        add_more = get_input("Add a seat class? (y/n)", required=False)
        if add_more.lower() != 'y':
            break
        
        seat_type = get_seat_type()
        total_seats = get_int_input("Total seats for this class")
        price = float(get_input("Price per seat"))
        
        seat_info_list.append(train_booking_pb2.SeatInfo(
            seat_type=seat_type,
            seats_available=total_seats,
            price=price
        ))
        
    if not seat_info_list:
        print("No seat classes added. Aborting.")
        return
        
    req = train_booking_pb2.AddTrainServiceRequest(
        admin_token=token,
        train_number=train_number,
        datetime_of_departure=dt_departure,
        datetime_of_arrival=dt_arrival,
        seat_info=seat_info_list
    )
    
    try:
        resp = call_with_leader_redirect("AddTrainService",req)
        print(f"\n{resp.message}")
    except grpc.RpcError as e:
        print(f"\nRPC Error: {e.details()}")

# --- Main Application ---

def run():
    """Main application loop."""
    # Connect to the server
    try:
        stub, channel = get_stub(current_node)
        # Check if server is running
        stub.ListCities(train_booking_pb2.ListCitiesRequest(), timeout=2)
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.UNAVAILABLE:
            print(f"Error: Cannot connect to the server at {current_node}.")
            print("Please ensure the server is running.")
            return
        else:
            print(f"Connection error: {e.details()}")
            return
            
    print("Welcome to the Train Booking System!")
    
    user_token = None
    user_role = None

    while True:
        print_main_menu(user_role)
        choice = get_input("Enter option")
        
        try:
            if user_token is None:
                # --- Logged-Out Menu ---
                if choice == '1':
                    user_token, user_role = do_login(stub)
                elif choice == '2':
                    do_register(stub)
                elif choice == '3':
                    do_list_cities(stub)
                elif choice == '4':
                    do_search_services(stub)
                elif choice == '5':
                    print("Goodbye!")
                    break
                else:
                    print("Invalid option, please try again.")
            
            elif user_role == "CUSTOMER":
                # --- Customer Menu ---
                if choice == '1':
                    do_search_and_book(stub, user_token)
                elif choice == '2':
                    do_view_bookings(stub, user_token)
                elif choice == '3':
                    do_ask_bot(stub, user_token)
                elif choice == '4':
                    user_token, user_role = do_logout(stub, user_token)
                else:
                    print("Invalid option, please try again.")
            
            elif user_role == "ADMIN":
                # --- Admin Menu ---
                if choice == '1':
                    do_add_train(stub, user_token)
                elif choice == '2':
                    do_add_service(stub, user_token)
                elif choice == '3':
                    user_token, user_role = do_logout(stub, user_token)
                else:
                    print("Invalid option, please try again.")
        
        except KeyboardInterrupt:
            print("\nCaught interrupt, logging out and exiting...")
            if user_token:
                do_logout(stub, user_token)
            break
        except Exception as e:
            print(f"\nAn unexpected error occurred: {e}")
            print("Please try again.")
            
    channel.close()

if __name__ == '__main__':
    run()
