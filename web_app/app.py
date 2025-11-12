from flask import Flask, render_template, jsonify, request, Response
import sys
import os
import json

# Add the project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import train_booking_pb2
import train_booking_pb2_grpc
from grpc_client import call_with_leader_redirect, call_streaming_rpc

app = Flask(__name__)

# Helper to convert gRPC SeatType enum (int) to a string
SEAT_TYPE_MAP = {
    0: 'UNKNOWN', 1: 'AC1', 2: 'AC2', 3: 'AC3', 4: 'GENERAL',
}

# --- HTML Page Routes ---

@app.route('/')
def home():
    """Serves the main HTML page."""
    return render_template('index.html')

# --- ================== ---
# --- API: UNARY CALLS ---
# --- ================== ---
# (Keep all your existing routes: /api/login, /api/register, /api/cities, etc.)
# ...

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    grpc_request = train_booking_pb2.LoginRequest(
        username=data.get('username'),
        password=data.get('password')
    )
    grpc_response = call_with_leader_redirect("Login", grpc_request)
    
    # We'll guess the role based on username for the UI
    role = "ADMIN" if "admin" in data.get('username', '').lower() else "CUSTOMER"
    
    return jsonify({
        "success": grpc_response.success,
        "message": grpc_response.message,
        "token": grpc_response.token,
        "role": role
    })

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.json
    grpc_request = train_booking_pb2.RegisterRequest(
        username=data.get('username'),
        password=data.get('password')
    )
    grpc_response = call_with_leader_redirect("Register", grpc_request)
    return jsonify({"success": grpc_response.success, "message": grpc_response.message})

@app.route('/api/cities', methods=['GET'])
def api_list_cities():
    grpc_request = train_booking_pb2.ListCitiesRequest()
    grpc_response = call_with_leader_redirect("ListCities", grpc_request)
    cities_list = [{"city_id": c.city_id, "city_name": c.city_name, "city_code": c.city_code} for c in grpc_response.cities]
    return jsonify(cities_list)

@app.route('/api/search', methods=['POST'])
def api_search():
    data = request.json
    grpc_request = train_booking_pb2.SearchRequest(
        source_city_id=int(data.get('source_city_id')),
        destination_city_id=int(data.get('destination_city_id')),
        date=data.get('date')
    )
    grpc_response = call_with_leader_redirect("SearchTrainServices", grpc_request)
    services_list = [{
        "service_id": s.service_id,
        "train_name": s.train_name,
        "source_city_name": s.source_city_name,
        "destination_city_name": s.destination_city_name,
        "datetime_of_departure": s.datetime_of_departure,
        "datetime_of_arrival": s.datetime_of_arrival,
        "seat_type": SEAT_TYPE_MAP.get(s.seat_type, 'UNKNOWN'),
        "seats_available": s.seats_available,
        "price": s.price
    } for s in grpc_response.services]
    return jsonify(services_list)

@app.route('/api/initiate_booking', methods=['POST'])
def api_initiate_booking():
    data = request.json
    grpc_request = train_booking_pb2.InitiateBookingRequest(
        customer_token=data.get('token'),
        service_id=data.get('service_id'),
        number_of_seats=int(data.get('num_seats'))
    )
    grpc_response = call_with_leader_redirect("InitiateBooking", grpc_request)
    return jsonify({
        "success": grpc_response.success,
        "message": grpc_response.message,
        "booking_id": grpc_response.booking_id,
        "total_cost": grpc_response.total_cost
    })

@app.route('/api/process_payment', methods=['POST'])
def api_process_payment():
    data = request.json
    grpc_request = train_booking_pb2.ProcessPaymentRequest(
        customer_token=data.get('token'),
        booking_id=data.get('booking_id'),
        payment_mode=data.get('payment_mode')
    )
    grpc_response = call_with_leader_redirect("ProcessPayment", grpc_request)
    return jsonify({"success": grpc_response.success, "message": grpc_response.message})

@app.route('/api/my_bookings', methods=['POST'])
def api_get_my_bookings():
    data = request.json
    grpc_request = train_booking_pb2.GetMyBookingsRequest(customer_token=data.get('token'))
    grpc_response = call_with_leader_redirect("GetMyBookings", grpc_request)
    bookings_list = [{
        "booking_id": b.booking_id,
        "train_name": b.train_name,
        "source": b.source,
        "destination": b.destination,
        "datetime_of_departure": b.datetime_of_departure,
        "number_of_seats": b.number_of_seats,
        "total_cost": b.total_cost,
        "status": b.status,
        "seat_type": SEAT_TYPE_MAP.get(b.seat_type, 'UNKNOWN')
    } for b in grpc_response.bookings]
    return jsonify(bookings_list)


# --- ================== ---
# --- API: ADMIN CALLS ---
# --- ================== ---

@app.route('/api/admin/add_train', methods=['POST'])
def api_add_train():
    data = request.json
    print(f"API: Admin request to add train {data.get('train_number')}")
    
    grpc_request = train_booking_pb2.AddTrainRequest(
        admin_token=data.get('token'),
        train_number=int(data.get('train_number')),
        train_name=data.get('train_name'),
        source_city_id=int(data.get('source_city_id')),
        destination_city_id=int(data.get('destination_city_id')),
        train_type=data.get('train_type')
    )
    grpc_response = call_with_leader_redirect("AddTrain", grpc_request)
    return jsonify({"success": grpc_response.success, "message": grpc_response.message})

@app.route('/api/admin/add_service', methods=['POST'])
def api_add_service():
    data = request.json
    print(f"API: Admin request to add service for train {data.get('train_number')}")

    # Convert seat_info from JSON list to gRPC repeated message
    seat_info_list = []
    for info in data.get('seat_info', []):
        seat_info_list.append(train_booking_pb2.SeatInfo(
            seat_type=train_booking_pb2.SeatType.Value(info.get('seat_type')), # "AC2" -> 2
            seats_available=int(info.get('seats_available')),
            price=float(info.get('price'))
        ))

    grpc_request = train_booking_pb2.AddTrainServiceRequest(
        admin_token=data.get('token'),
        train_number=int(data.get('train_number')),
        datetime_of_departure=data.get('datetime_of_departure'),
        datetime_of_arrival=data.get('datetime_of_arrival'),
        seat_info=seat_info_list
    )
    grpc_response = call_with_leader_redirect("AddTrainService", grpc_request)
    return jsonify({"success": grpc_response.success, "message": grpc_response.message})


# --- ====================== ---
# --- API: STREAMING CALLS ---
# --- ====================== ---

@app.route('/api/ask_bot', methods=['POST'])
def api_ask_bot():
    """
    Handles the streaming chatbot request.
    This uses a special streaming response.
    """
    data = request.json
    grpc_request = train_booking_pb2.LLMQuery(
        customer_token=data.get('token'),
        query=data.get('query')
    )
    
    # This generator function will stream data to the browser
    def stream_response_generator():
        for chunk in call_streaming_rpc("AskBot", grpc_request):
            data_payload = json.dumps({"answer": chunk.answer})
            yield f"data: {data_payload}\n\n"
        # Signal the end of the stream
        yield "data: [STREAM_END]\n\n"

    # Return a streaming response
    return Response(stream_response_generator(), mimetype='text/event-stream')


if __name__ == '__main__':
    app.run(debug=True, port=8000)