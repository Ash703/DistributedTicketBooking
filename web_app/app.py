from flask import Flask, render_template, jsonify, request
import sys
import os

# Add the project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import train_booking_pb2
import train_booking_pb2_grpc
from web_app.grpc_client import call_with_leader_redirect # Import from the local file

app = Flask(__name__)

# --- HTML Page Routes ---

@app.route('/')
def home():
    """Serves the main HTML page."""
    return render_template('index.html')

# --- API Routes (for JavaScript to call) ---

@app.route('/api/cities', methods=['GET'])
def api_list_cities():
    """API endpoint to get the list of cities."""
    print("API: Received request for /api/cities")
    grpc_request = train_booking_pb2.ListCitiesRequest()
    grpc_response = call_with_leader_redirect("ListCities", grpc_request)
    
    cities_list = [
        {
            "city_id": city.city_id,
            "city_name": city.city_name,
            "city_code": city.city_code
        } for city in grpc_response.cities
    ]
    return jsonify(cities_list)

@app.route('/api/register', methods=['POST'])
def api_register():
    """API endpoint for new user registration."""
    data = request.json
    print(f"API: Received request for /api/register for user '{data.get('username')}'")
    
    # 1. Create the gRPC request
    grpc_request = train_booking_pb2.RegisterRequest(
        username=data.get('username'),
        password=data.get('password')
    )
    
    # 2. Call the gRPC backend
    grpc_response = call_with_leader_redirect("Register", grpc_request)
    
    # 3. Return the result as JSON
    return jsonify({
        "success": grpc_response.success,
        "message": grpc_response.message
    })

@app.route('/api/login', methods=['POST'])
def api_login():
    """API endpoint for user login."""
    data = request.json
    print(f"API: Received request for /api/login for user '{data.get('username')}'")

    # 1. Create the gRPC request
    grpc_request = train_booking_pb2.LoginRequest(
        username=data.get('username'),
        password=data.get('password')
    )
    
    # 2. Call the gRPC backend
    grpc_response = call_with_leader_redirect("Login", grpc_request)
    
    # 3. Return the result as JSON
    return jsonify({
        "success": grpc_response.success,
        "message": grpc_response.message,
        "token": grpc_response.token
    })

if __name__ == '__main__':
    app.run(debug=True, port=8000)