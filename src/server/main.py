import asyncio
import grpc
import train_booking_pb2_grpc
from services.booking_service import BookingService
from database import connection as db_connection


async def serve():
    """
    Starts the async gRPC server and waits for requests.
    """
    await db_connection.init_db()  # async DB initialization

    server = grpc.aio.server()  # Async gRPC server
    train_booking_pb2_grpc.add_TicketingServicer_to_server(BookingService(), server)
    server.add_insecure_port('[::]:50051')

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
    asyncio.run(serve())
