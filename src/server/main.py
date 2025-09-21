from concurrent import futures
import grpc
import time
import train_booking_pb2_grpc
from .services.booking_service import BookingService
from .database import connection as db_connection

def serve():
    """
    Starts the gRPC server and waits for requests.
    """

    db_connection.init_db()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    train_booking_pb2_grpc.add_TicketingServicer_to_server(BookingService(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    print("Server started successfully on port 50051.")
    try:
        while True:
            time.sleep(86400) 
    except KeyboardInterrupt:
        server.stop(0)
        print("Server stopped.")

if __name__ == '__main__':
    serve()