import grpc
import train_booking_pb2
import train_booking_pb2_grpc
import re

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
    """
    global current_node
    if "not the leader" in response_message.lower():
        print(f"[Flask gRPC] Redirecting: {response_message}")
        match = re.search(r"leader\s+(\d+)", response_message)
        if match:
            leader_id = match.group(1)
            # Find the full address from the ID
            new_node_port = f"5005{leader_id}"
            new_node_addr = next((n for n in NODES if new_node_port in n), None)
            
            if new_node_addr and new_node_addr != current_node:
                print(f"[Flask gRPC] Redirecting to new leader: {new_node_addr}")
                current_node = new_node_addr
                return True
    return False

def call_with_leader_redirect(rpc_name, request, max_retries=3):
    """
    Calls a gRPC RPC with automatic leader redirection and node failover.
    (This is your code, slightly modified for Flask logging)
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
            print(f"[Flask gRPC] RPC Error from {current_node}: {details or code.name}")

            if code in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
                tried_nodes.add(current_node)
                next_candidates = [n for n in NODES if n not in tried_nodes]
                if not next_candidates:
                    print("[Flask gRPC] All nodes unreachable. Cluster may be down.")
                    break
                current_node = next_candidates[0]
                print(f"[Flask gRPC] Retrying on next node: {current_node}")
                attempt += 1
                continue
            else:
                break  # Non-retryable error
        finally:
            channel.close()

    # Fallback response for web app to understand
    class FallbackResponse:
        def __init__(self, message="All nodes unreachable or request failed."):
            self.success = False
            self.message = message
            # Add all other possible fields to prevent AttributeErrors
            self.token = ""
            self.cities = []
            self.services = []
            self.bookings = []
            self.answer = message
            self.booking_id = ""
            self.total_cost = 0.0
            self.trains = []

    return FallbackResponse()

# --- NEW: Separate function for streaming RPCs ---
# Your call_with_leader_redirect won't work for streams.
# This function calls the *current_node* and yields results.
# If it fails, the JavaScript will need to handle the error.
def call_streaming_rpc(rpc_name, request):
    """
    Handles streaming RPCs, like the chatbot.
    Does NOT currently handle leader redirection, but calls the known leader.
    """
    global current_node
    stub, channel = get_stub(current_node)
    
    print(f"[Flask gRPC] Starting stream '{rpc_name}' to {current_node}")
    try:
        rpc_method = getattr(stub, rpc_name)
        response_stream = rpc_method(request)
        
        for chunk in response_stream:
            yield chunk
            
    except grpc.RpcError as e:
        print(f"[Flask gRPC] Stream RPC Error: {e.details()}")
        # Yield an error message to the client
        yield train_booking_pb2.LLMAnswer(answer=f"[STREAM ERROR: {e.details()}]")
    finally:
        channel.close()