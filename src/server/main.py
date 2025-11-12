import asyncio
import grpc
import train_booking_pb2_grpc
from raft.raft_node import RaftNode
from services.booking_service import BookingService
from database import connection as db_connection
from utils import config

async def serve(node_id, port, peers):
    """
    Starts the async gRPC server and waits for requests.
    Includes graceful shutdown logic.
    """
    config.DB_NAME = f"Node{node_id}" + config.DB_NAME
    await db_connection.init_db() 

    raft_node = RaftNode(node_id=node_id, peers=peers)

    server = grpc.aio.server()  # Async gRPC server
    train_booking_pb2_grpc.add_TicketingServicer_to_server(BookingService(raft_node), server)
    train_booking_pb2_grpc.add_RaftServicer_to_server(raft_node, server)

    server.add_insecure_port(f'[::]:{port}')

    print(f"Starting async gRPC server on port {port}...")
    await server.start()

    print(f"Server started successfully on port {port}.")
    
    # Start the Raft node's main loop as a background task
    # This assumes raft_node.start() is the long-running async function
    raft_task = asyncio.create_task(raft_node.start())
    print(f"Node {node_id} Raft protocol task started.")

    try:
        # This will wait indefinitely until the server is shut down
        await server.wait_for_termination()
        
    except asyncio.CancelledError:
        # This exception is raised when asyncio.run() catches the KeyboardInterrupt
        print(f"\nShutdown signal (CancelledError) received on node {node_id}...")
        
    finally:
        # This block will run regardless of how the try block exited,
        # ensuring a clean shutdown.
        
        print("Stopping gRPC server...")
        # Gracefully stop the server, waiting 1 second for calls to finish
        await server.stop(1)
        
        # Cancel and clean up the background Raft task
        if not raft_task.done():
            raft_task.cancel()
            try:
                await raft_task # Await the cancellation to complete
            except asyncio.CancelledError:
                pass # This is expected when cancelling
        
        print(f"Node {node_id} server and Raft task stopped.")


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

    try:
        # asyncio.run() will catch the KeyboardInterrupt and
        # correctly trigger the CancelledError inside serve()
        asyncio.run(serve(current["id"], current["port"], peers))
    except KeyboardInterrupt:
        # This block will run after serve() has already cleaned up
        print(f"\nNode {current['id']} main process exiting...")