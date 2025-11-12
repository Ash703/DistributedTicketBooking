import streamlit as st
import grpc
import train_booking_pb2
import train_booking_pb2_grpc
import re
import pandas as pd
import asyncio

# --- gRPC Client Logic (Adapted from your CLI) ---
# This section contains your fault-tolerant client logic,
# modified to use Streamlit's session_state instead of global variables.

NODES = ["localhost:50051", "localhost:50052", "localhost:50053"]

def get_stub(address):
    """Creates a stub for a given node address."""
    channel = grpc.insecure_channel(address)
    return train_booking_pb2_grpc.TicketingStub(channel), channel

def detect_and_redirect_if_not_leader(response_message):
    """
    Detects 'not leader' message and updates the session_state.
    """
    if "not the leader" in response_message.lower():
        match = re.search(r"leader\s+(\d+)", response_message)
        if match:
            leader_id = match.group(1)
            # Find the full address from the ID
            new_node_port = f"5005{leader_id}"
            new_node_addr = next((n for n in NODES if new_node_port in n), None)
            
            if new_node_addr and new_node_addr != st.session_state.current_node:
                st.info(f"Redirecting to new leader node at {new_node_addr}...")
                st.session_state.current_node = new_node_addr
                return True
    return False

def call_with_leader_redirect(rpc_name, request, max_retries=3):
    """
    Calls a unary gRPC RPC with leader redirection and failover,
    using st.session_state to manage the current leader.
    """
    attempt = 0
    tried_nodes = set()

    while attempt < max_retries:
        current_node = st.session_state.current_node
        stub, channel = get_stub(current_node)
        try:
            rpc_method = getattr(stub, rpc_name)
            resp = rpc_method(request)

            if hasattr(resp, "message") and "not the leader" in resp.message.lower():
                if detect_and_redirect_if_not_leader(resp.message):
                    channel.close()
                    st.rerun() # Re-run the script to try the new leader
            
            return resp

        except grpc.RpcError as e:
            code = e.code()
            details = e.details() or ""
            st.error(f"RPC Error from {current_node}: {details or code.name}")

            if code in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
                tried_nodes.add(current_node)
                next_candidates = [n for n in NODES if n not in tried_nodes]
                if not next_candidates:
                    st.error("All nodes unreachable. Cluster may be down.")
                    break
                st.session_state.current_node = next_candidates[0]
                st.info(f"Retrying on next node: {st.session_state.current_node}")
                attempt += 1
                continue
            else:
                break  # Non-retryable error
        finally:
            channel.close()

    # Fallback response
    class FallbackResponse:
        def __init__(self, message="All nodes unreachable or request failed."):
            self.success = False
            self.message = message
            self.token = ""
            self.cities = []
            self.services = []
            self.bookings = []
            self.answer = message
            self.booking_id = ""
            self.total_cost = 0.0
    return FallbackResponse()

async def async_call_streaming_rpc(rpc_name, request):
    """
    Handles streaming RPCs (like the chatbot) asynchronously.
    Calls the current known leader from session_state.
    """
    current_node = st.session_state.current_node
    try:
        async with grpc.aio.insecure_channel(current_node) as channel:
            stub = train_booking_pb2_grpc.TicketingStub(channel)
            rpc_method = getattr(stub, rpc_name)
            response_stream = rpc_method(request)
            
            async for chunk in response_stream:
                yield chunk.answer
                
    except grpc.aio.AioRpcError as e:
        st.error(f"Stream RPC Error: {e.details()}")
        yield f"[STREAM ERROR: {e.details()}]"

# --- Streamlit UI ---

# Page config
st.set_page_config(layout="wide", page_title="Distributed Train Booking")

# Initialize session state
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.token = None
    st.session_state.role = None
    st.session_state.username = None
    st.session_state.current_node = NODES[0]
    st.session_state.chat_messages = []

# --- Authentication UI (Sidebar) ---
st.sidebar.title("Train Booking System")

if not st.session_state.logged_in:
    st.sidebar.header("Login")
    login_username = st.sidebar.text_input("Username", key="login_user")
    login_password = st.sidebar.text_input("Password", type="password", key="login_pass")
    
    if st.sidebar.button("Login"):
        req = train_booking_pb2.LoginRequest(username=login_username, password=login_password)
        resp = call_with_leader_redirect("Login", req)
        
        if resp.success:
            st.session_state.logged_in = True
            st.session_state.token = resp.token
            st.session_state.username = login_username
            # Simple role detection (matches your CLI client)
            st.session_state.role = "ADMIN" if "admin" in login_username.lower() else "CUSTOMER"
            st.rerun()
        else:
            st.sidebar.error(f"Login failed: {resp.message}")

    st.sidebar.header("Register")
    reg_username = st.sidebar.text_input("New Username", key="reg_user")
    reg_password = st.sidebar.text_input("New Password", type="password", key="reg_pass")
    
    if st.sidebar.button("Register"):
        req = train_booking_pb2.RegisterRequest(username=reg_username, password=reg_password)
        resp = call_with_leader_redirect("Register", req)
        if resp.success:
            st.sidebar.success(f"{resp.message} Please log in.")
        else:
            st.sidebar.error(f"Registration failed: {resp.message}")
else:
    st.sidebar.success(f"Welcome, {st.session_state.username} ({st.session_state.role})")
    st.sidebar.info(f"Connected to node: {st.session_state.current_node}")
    if st.sidebar.button("Logout"):
        # We don't need to call the RPC, just clear the session
        st.session_state.logged_in = False
        st.session_state.token = None
        st.session_state.role = None
        st.session_state.username = None
        st.session_state.chat_messages = []
        st.rerun()

# --- Main Application UI (Tabs) ---

# Caches the list of cities
@st.cache_data(ttl=300)
def get_city_data():
    """Fetches and caches the list of cities from the gRPC server."""
    print("Caching: Fetching city list")
    grpc_request = train_booking_pb2.ListCitiesRequest()
    grpc_response = call_with_leader_redirect("ListCities", grpc_request)
    # Convert to a list of dicts for Streamlit widgets
    return [{"id": c.city_id, "name": f"{c.city_name} ({c.city_code})"} for c in grpc_response.cities]

if st.session_state.logged_in:
    
    # Load city data once
    try:
        city_list = get_city_data()
        city_map = {c["name"]: c["id"] for c in city_list}
        city_names = list(city_map.keys())
    except Exception as e:
        st.error(f"Failed to load initial city data: {e}")
        st.stop()

    if st.session_state.role == "CUSTOMER":
        tab1, tab2, tab3 = st.tabs(["Search & Book", "My Bookings", "Chatbot"])

        with tab1:
            st.header("Search and Book a Train")
            with st.form("search_form"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    from_city_name = st.selectbox("From", options=city_names, index=None, placeholder="Select Departure City")
                with col2:
                    to_city_name = st.selectbox("To", options=city_names, index=None, placeholder="Select Destination City")
                with col3:
                    search_date = st.date_input("Date")
                
                search_submitted = st.form_submit_button("Search", use_container_width=True)
            
            if search_submitted:
                if not from_city_name or not to_city_name:
                    st.warning("Please select both departure and destination cities.")
                else:
                    req = train_booking_pb2.SearchRequest(
                        source_city_id=city_map[from_city_name],
                        destination_city_id=city_map[to_city_name],
                        date=search_date.strftime("%Y-%m-%d")
                    )
                    resp = call_with_leader_redirect("SearchTrainServices", req)
                    
                    if not resp.services:
                        st.info("No services found for this route and date.")
                    else:
                        st.subheader("Search Results")
                        # Store results in session state to handle booking
                        st.session_state.search_results = resp.services
                        
                        # Prepare data for display
                        display_data = []
                        for i, s in enumerate(resp.services):
                            display_data.append({
                                "Select": i + 1,
                                "Train": s.train_name,
                                "From": s.source_city_name,
                                "To": s.destination_city_name,
                                "Departs": s.datetime_of_departure,
                                "Arrives": s.datetime_of_arrival,
                                "Class": train_booking_pb2.SeatType.Name(s.seat_type),
                                "Seats": s.seats_available,
                                "Price": f"{s.price:.2f}"
                            })
                        st.dataframe(pd.DataFrame(display_data), use_container_width=True)

            # --- Booking Section ---
            if "search_results" in st.session_state and st.session_state.search_results:
                st.write("---")
                st.subheader("Book a Ticket")
                col1, col2 = st.columns([1, 2])
                with col1:
                    choice_index = st.number_input("Enter 'Select' number to book", min_value=1, max_value=len(st.session_state.search_results), step=1)
                with col2:
                    num_seats = st.number_input("Number of seats", min_value=1, value=1, step=1)
                
                if st.button("Initiate Booking"):
                    service_to_book = st.session_state.search_results[choice_index - 1]
                    with st.spinner("Reserving seats..."):
                        init_req = train_booking_pb2.InitiateBookingRequest(
                            customer_token=st.session_state.token,
                            service_id=service_to_book.service_id,
                            number_of_seats=num_seats
                        )
                        init_resp = call_with_leader_redirect("InitiateBooking", init_req)
                        
                        if init_resp.success:
                            st.session_state.pending_booking_id = init_resp.booking_id
                            st.success(f"Booking Initiated! Total cost: {init_resp.total_cost:.2f}. Please confirm payment.")
                        else:
                            st.error(f"Booking Failed: {init_resp.message}")
            
            if "pending_booking_id" in st.session_state:
                if st.button("Confirm Payment (Mock)"):
                    with st.spinner("Processing payment..."):
                        pay_req = train_booking_pb2.ProcessPaymentRequest(
                            customer_token=st.session_state.token,
                            booking_id=st.session_state.pending_booking_id,
                            payment_mode="StreamlitPay"
                        )
                        pay_resp = call_with_leader_redirect("ProcessPayment", pay_req)
                        if pay_resp.success:
                            st.success(f"Payment Confirmed! {pay_resp.message}")
                            del st.session_state.pending_booking_id
                            del st.session_state.search_results
                        else:
                            st.error(f"Payment Failed: {pay_resp.message}")

        with tab2:
            st.header("My Bookings")
            if st.button("Refresh My Bookings"):
                req = train_booking_pb2.GetMyBookingsRequest(customer_token=st.session_state.token)
                resp = call_with_leader_redirect("GetMyBookings", req)
                
                if not resp.bookings:
                    st.info("You have no bookings.")
                else:
                    display_data = []
                    for b in resp.bookings:
                        display_data.append({
                            "Booking ID": b.booking_id[:8] + "...",
                            "Train": b.train_name,
                            "From": b.source,
                            "To": b.destination,
                            "Date": b.datetime_of_departure,
                            "Seats": b.number_of_seats,
                            "Cost": b.total_cost,
                            "Status": b.status
                        })
                    st.dataframe(pd.DataFrame(display_data), use_container_width=True)

        with tab3:
            st.header("Chatbot")
            
            # Display chat history
            for msg in st.session_state.chat_messages:
                with st.chat_message(msg["role"]):
                    st.write(msg["content"])
            
            # Chat input
            if query := st.chat_input("Ask about your bookings or available trains..."):
                # Add user message to history
                st.session_state.chat_messages.append({"role": "user", "content": query})
                with st.chat_message("user"):
                    st.write(query)
                
                # Prepare gRPC request
                req = train_booking_pb2.LLMQuery(customer_token=st.session_state.token, query=query)
                
                # Add "assistant" message and stream response
                with st.chat_message("assistant"):
                    # st.write_stream is the key for streaming
                    response_generator = async_call_streaming_rpc("AskBot", req)
                    full_response = st.write_stream(response_generator)
                
                # Add full response to history
                st.session_state.chat_messages.append({"role": "assistant", "content": full_response})

    elif st.session_state.role == "ADMIN":
        tab1, tab2 = st.tabs(["Add Train", "Add Service"])

        with tab1:
            st.header("Add New Train Route")
            with st.form("add_train_form"):
                train_number = st.number_input("Train Number", min_value=1000, step=1)
                train_name = st.text_input("Train Name")
                from_city_name = st.selectbox("From", options=city_names, index=None, placeholder="Select Departure City", key="admin_from")
                to_city_name = st.selectbox("To", options=city_names, index=None, placeholder="Select Destination City", key="admin_to")
                train_type = st.selectbox("Train Type", options=["Express", "Superfast", "Rajdhani", "Duronto", "Shatabdi", "Garib Rath", "Special", "Mail"])
                
                train_submitted = st.form_submit_button("Add Train", use_container_width=True)
                
                if train_submitted:
                    if not all([train_number, train_name, from_city_name, to_city_name, train_type]):
                        st.warning("Please fill out all fields.")
                    else:
                        req = train_booking_pb2.AddTrainRequest(
                            admin_token=st.session_state.token,
                            train_number=train_number,
                            train_name=train_name,
                            source_city_id=city_map[from_city_name],
                            destination_city_id=city_map[to_city_name],
                            train_type=train_type
                        )
                        resp = call_with_leader_redirect("AddTrain", req)
                        if resp.success:
                            st.success(resp.message)
                        else:
                            st.error(resp.message)
        
        with tab2:
            st.header("Add New Train Service (Schedule)")
            
            with st.form("add_service_form"):
                train_number_svc = st.number_input("Train Number (must exist)", min_value=1000, step=1)
                departure = st.text_input("Departure Datetime (YYYY-MM-DD HH:MM:SS)")
                arrival = st.text_input("Arrival Datetime (YYYY-MM-DD HH:MM:SS)")
                
                st.subheader("Seat Classes")
                # Use st.data_editor to handle a list of seat classes
                if "seat_info" not in st.session_state:
                    st.session_state.seat_info = pd.DataFrame([
                        {"Class": "AC2", "Total Seats": 50, "Price": 2500.00}
                    ])
                
                edited_seats = st.data_editor(
                    st.session_state.seat_info,
                    num_rows="dynamic",
                    column_config={
                        "Class": st.column_config.SelectboxColumn("Class", options=["AC1", "AC2", "AC3", "GENERAL"], required=True),
                        "Total Seats": st.column_config.NumberColumn("Total Seats", min_value=0, step=1, required=True),
                        "Price": st.column_config.NumberColumn("Price", min_value=0.0, format="%.2f", required=True)
                    }
                )
                
                service_submitted = st.form_submit_button("Add Service Schedule", use_container_width=True)
                
                if service_submitted:
                    # Convert dataframe to gRPC message
                    seat_info_list = []
                    for _, row in edited_seats.iterrows():
                        seat_info_list.append(train_booking_pb2.SeatInfo(
                            seat_type=train_booking_pb2.SeatType.Value(row["Class"]),
                            seats_available=int(row["Total Seats"]),
                            price=float(row["Price"])
                        ))
                    
                    if not seat_info_list:
                        st.warning("Please add at least one seat class.")
                    else:
                        req = train_booking_pb2.AddTrainServiceRequest(
                            admin_token=st.session_state.token,
                            train_number=train_number_svc,
                            datetime_of_departure=departure,
                            datetime_of_arrival=arrival,
                            seat_info=seat_info_list
                        )
                        resp = call_with_leader_redirect("AddTrainService", req)
                        if resp.success:
                            st.success(resp.message)
                            st.session_state.seat_info = pd.DataFrame([{"Class": "AC2", "Total Seats": 50, "Price": 2500.00}])
                        else:
                            st.error(resp.message)

else:
    st.header("Welcome!")
    st.info("Please log in or register using the sidebar to continue.")