import grpc
import train_booking_pb2
import train_booking_pb2_grpc
import re

# Your gRPC Raft cluster nodes
NODES = ["localhost:50051", "localhost:50052", "localhost:50053"]
current_node = NODES[0]

def get_stub(address):
    """Creates a stub for a given node address."""
    channel = grpc.insecure_channel(address)
    return train_booking_pb2_grpc.TicketingStub(channel), channel

def call_with_leader_redirect(rpc_name, request, max_retries=3):
    """
    Calls a gRPC RPC with automatic leader redirection and node failover.
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
                print(f"Info: {resp.message}")
                match = re.search(r"leader\s+(\d+)", resp.message)
                if match:
                    leader_id = match.group(1)
                    # Assumes node ID '1' is 'localhost:50051'
                    new_node = f"localhost:5005{leader_id}"
                    if new_node in NODES and new_node != current_node:
                        print(f"Redirecting to leader node at {new_node}...\n")
                        current_node = new_node
                        channel.close()
                        continue # Retry the call with the new leader node
            
            channel.close()
            return resp

        except grpc.RpcError as e:
            code = e.code()
            details = e.details() or ""
            print(f"RPC Error from {current_node}: {details or code.name}")

            if code in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
                tried_nodes.add(current_node)
                next_candidates = [n for n in NODES if n not in tried_nodes]
                if not next_candidates:
                    print("All nodes unreachable.")
                    break
                current_node = next_candidates[0]
                print(f"Retrying on next node: {current_node}")
                attempt += 1
                continue
            else:
                break # Non-retryable error
        finally:
            channel.close()

    # Fallback response if all retries fail
    class FallbackResponse:
        def __init__(self, message="All nodes unreachable or request failed."):
            self.success = False
            self.message = message
            # Add other common fields to avoid AttributeError
            self.token = ""
            self.cities = []
            self.services = []
            self.bookings = []
            self.answer = "Request failed."

    return FallbackResponse()