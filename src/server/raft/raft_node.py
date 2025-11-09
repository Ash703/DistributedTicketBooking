import asyncio
import random
import grpc
import train_booking_pb2
import train_booking_pb2_grpc

class RaftNode(train_booking_pb2_grpc.RaftServicer):
    def __init__(self, node_id, peers):
        self.node_id = str(node_id)
        self.peers = peers  # list of "host:port"
        self.state = "follower"
        self.current_term = 0
        self.voted_for = None
        self.log = []
        self.commit_index = 0
        self.last_applied = 0
        self.leader_id = None

        self.heartbeat_received = asyncio.Event()
        self.running = True

    async def start(self):
        asyncio.create_task(self.election_timer())
        asyncio.create_task(self.heartbeat_loop())

    async def election_timer(self):
        """Manages election timeout and starts elections when needed."""
        while self.running:
            timeout = random.uniform(3.0, 6.0) + random.random() * int(self.node_id)  # seconds
            try:
                await asyncio.wait_for(self.heartbeat_received.wait(), timeout)
                self.heartbeat_received.clear()
            except asyncio.TimeoutError:
                print(f"[{self.node_id}] Election timeout. Starting election.")
                await self.start_election()

    async def start_election(self):
        """Initiate an election for leadership."""
        self.state = "candidate"
        self.current_term += 1
        self.voted_for = self.node_id
        votes = 1
        self.heartbeat_received.clear()
        tasks = []
        for peer in self.peers:
            tasks.append(self.request_vote_from_peer(peer))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, train_booking_pb2.VoteResponse) and r.vote_granted:
                votes += 1

        if votes > (len(self.peers) + 1) // 2:
            print(f"[{self.node_id}] Became leader (term {self.current_term})")
            self.state = "leader"
            self.leader_id = self.node_id
            self.heartbeat_received.clear()
        else:
            print(f"[{self.node_id}] Election failed with {votes} votes.")

    async def request_vote_from_peer(self, peer):
        if isinstance(peer, tuple):
            peer = f"{peer[0]}:{peer[1]}"  # convert tuple → "host:port"

        try:
            async with grpc.aio.insecure_channel(peer) as channel:
                stub = train_booking_pb2_grpc.RaftStub(channel)
                req = train_booking_pb2.VoteRequest(
                    term=self.current_term,
                    candidate_id=self.node_id,
                    last_log_index=len(self.log),
                    last_log_term=self.log[-1].term if self.log else 0
                )
                return await stub.RequestVote(req)
        except Exception as e:
            print(f"[{self.node_id}] Failed to contact {peer}: {e}")

    async def RequestVote(self, request, context):
        """Handle incoming vote requests."""
        if request.term < self.current_term:
            return train_booking_pb2.VoteResponse(term=self.current_term, vote_granted=False)
        
        if request.term > self.current_term:
            self.current_term = request.term
            self.voted_for = None
            self.state = "follower"

        if (self.voted_for is None or self.voted_for == request.candidate_id):
            self.voted_for = request.candidate_id
            self.current_term = request.term
            print(f"[{self.node_id}] Voted for {request.candidate_id} (term {request.term})")
            return train_booking_pb2.VoteResponse(term=self.current_term, vote_granted=True)

        return train_booking_pb2.VoteResponse(term=self.current_term, vote_granted=False)

    async def AppendEntries(self, request, context):
        """Handle heartbeat and log replication."""
        if request.term < self.current_term:
            return train_booking_pb2.AppendEntriesResponse(term=self.current_term, success=False)
        
        print(f"[{self.node_id}] Received heartbeat from {request.leader_id} (term {request.term})")
        self.heartbeat_received.set()
        self.state = "follower"
        self.current_term = request.term
        self.leader_id = request.leader_id

        return train_booking_pb2.AppendEntriesResponse(term=self.current_term, success=True)

    async def heartbeat_loop(self):
        """Leaders send heartbeats periodically."""
        while self.running:
            if self.state == "leader":
                await self.send_heartbeats()
            await asyncio.sleep(2.0)

    async def send_heartbeats(self):
        """Send AppendEntries RPCs to all peers."""
        for peer in self.peers:
            asyncio.create_task(self.append_entries_to_peer(peer))

    async def append_entries_to_peer(self, peer):
        if isinstance(peer, tuple):
            peer = f"{peer[0]}:{peer[1]}"  # convert tuple → "host:port"

        try:
            async with grpc.aio.insecure_channel(peer) as channel:
                stub = train_booking_pb2_grpc.RaftStub(channel)
                req = train_booking_pb2.AppendEntriesRequest(
                    term=self.current_term,
                    leader_id=self.node_id,
                    prev_log_index=len(self.log),
                    prev_log_term=self.log[-1].term if self.log else 0,
                    entries=[],  # empty means heartbeat
                    leader_commit=self.commit_index
                )
                await stub.AppendEntries(req)
        except Exception as e:
            print(f"[{self.node_id}] Heartbeat to {peer} failed: \n{e}")
