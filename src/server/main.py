import asyncio
import grpc
import train_booking_pb2_grpc
from raft.raft_node import RaftNode
from services.booking_service import BookingService
from database import connection as db_connection


async def serve(node_id, port, peers):
    """
    Starts the async gRPC server and waits for requests.
    """
    await db_connection.init_db()  # async DB initialization

    server = grpc.aio.server()  # Async gRPC server
    train_booking_pb2_grpc.add_TicketingServicer_to_server(BookingService(), server)

    raft_node = RaftNode(node_id=node_id, peers=peers)
    train_booking_pb2_grpc.add_RaftServicer_to_server(raft_node, server)
    await raft_node.start()

    server.add_insecure_port(f'[::]:{port}')

    print("Starting async gRPC server on port 50051...")
    await server.start()

    print("Server started successfully on port 50051.")
    try:
        # Wait indefinitely
        await server.wait_for_termination()
    except KeyboardInterrupt:
        print("Server shutting down...")
        await server.stop(0)
        print("Server stopped.")


if __name__ == '__main__':
    import sys
    nodes = [
        {"id": 1, "port": 50051},
        {"id": 2, "port": 50052},
        {"id": 3, "port": 50053},
    ]

    node_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    current = next(n for n in nodes if n["id"] == node_id)
    peers = [(f"localhost", n["port"]) for n in nodes if n["id"] != node_id]

    asyncio.run(serve(current["id"], current["port"], peers))