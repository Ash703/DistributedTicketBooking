import asyncio
import random
import grpc
import train_booking_pb2
import train_booking_pb2_grpc
from dataclasses import dataclass
import json
import os

@dataclass
class RaftLogEntry:
    term: int
    command: str

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
        self.log: list[RaftLogEntry] = []
        self.db_lock = asyncio.Lock()
        self.apply_lock = asyncio.Lock()
        self.applying = False
        self.next_index = {}
        self.match_index = {}

        self.heartbeat_received = asyncio.Event()
        self.running = True

        # Persistent state file
        self.state_file = f"raft_state_node{self.node_id}.json"

        # Load previous state if exists
        self.load_state()

    async def start(self):
        asyncio.create_task(self.election_timer())
        asyncio.create_task(self.heartbeat_loop())

    def load_state(self):
        """Load Raft term, vote, and log from disk if available."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                    self.current_term = data.get("current_term", 0)
                    self.voted_for = data.get("voted_for")
                    self.log = [
                        train_booking_pb2.LogEntry(
                            command=e["command"], term=e["term"]
                        )
                        for e in data.get("log", [])
                    ]
                    self.last_applied = data.get("last_applied_index", 0)
                print(f"[{self.node_id}] Loaded persistent state: term={self.current_term}, log_len={len(self.log)}")
            except Exception as e:
                print(f"[{self.node_id}] Failed to load state: {e}")

    def save_state(self):
        """Persist current term, vote, and log to disk."""
        try:
            with open(self.state_file, "w") as f:
                data = {
                    "current_term": self.current_term,
                    "voted_for": self.voted_for,
                    "log": [{"term": e.term, "command": e.command} for e in self.log],
                    "last_applied_index": self.last_applied
                }
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[{self.node_id}] Failed to save state: {e}")

    async def election_timer(self):
        """Manages election timeout and starts elections when needed."""
        while self.running:
            if self.state == "leader":
                await asyncio.sleep(1.0)
                continue
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
        self.save_state()
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

            for peer in self.peers:
                if isinstance(peer, tuple):
                    peer = f"{peer[0]}:{peer[1]}"
                self.next_index[peer] = len(self.log)
                self.match_index[peer] = 0

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
            # print(f"[{self.node_id}] Failed to contact {peer}: {e}")
            print(f"[{self.node_id}] Failed to contact {peer}: Server may be down.")

    async def RequestVote(self, request, context):
        """Handle incoming vote requests."""
        if request.term < self.current_term:
            return train_booking_pb2.VoteResponse(term=self.current_term, vote_granted=False)
        
        if request.term > self.current_term:
            self.current_term = int(request.term)
            self.voted_for = None
            self.state = "follower"
            self.save_state()

        if (self.voted_for is None) or (self.voted_for == request.candidate_id):
            self.voted_for = request.candidate_id
            self.current_term = int(request.term)
            self.state = "follower"
            self.save_state()
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
        self.voted_for = None

        self.save_state()

        # --- Log replication: append any new entries ---
        # request.prev_log_index is the number of entries before these entries (0 if none)
        prev_log_index = int(request.prev_log_index)
        prev_log_term = int(request.prev_log_term)

        # If the follower is missing entries up to prev_log_index, reject
        if prev_log_index > len(self.log):
            # follower missing entries entirely
            return train_booking_pb2.AppendEntriesResponse(term=self.current_term, success=False)

        # If prev_log_index > 0, check term matches
        if prev_log_index > 0:
            local_term = self.log[prev_log_index - 1].term
            if local_term != prev_log_term:
                # truncate conflicting entries
                self.log = self.log[:prev_log_index]
                self.save_state()
                return train_booking_pb2.AppendEntriesResponse(term=self.current_term, success=False)

        # Append entries (avoid duplicates / overwrite if necessary)
        # request.entries are protobuf LogEntry objects
        idx = prev_log_index  # 0-based index where we will append first new entry
        for incoming in request.entries:
            # If the follower already has an entry at this index
            if idx < len(self.log):
                # If terms differ, overwrite from here
                if self.log[idx].term != incoming.term:
                    # delete remainder and append
                    self.log = self.log[:idx]
                    self.log.append(train_booking_pb2.LogEntry(command=incoming.command, term=incoming.term))
            else:
                # follower doesn't have this entry yet
                self.log.append(train_booking_pb2.LogEntry(command=incoming.command, term=incoming.term))
            idx += 1

        # Update commit index to leader_commit if leader sent higher
        leader_commit = int(request.leader_commit)
        if leader_commit > self.commit_index:
            # commit up to leader_commit (bounded by len(log))
            self.commit_index = min(leader_commit, len(self.log))

        # persist updated log / term / vote
        self.save_state()

        # Apply newly committed entries to local DB
        # Note: apply_log_entries will process from last_applied up to commit_index
        if self.commit_index > self.last_applied and not self.applying:
            asyncio.create_task(self.apply_log_entries())

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
            asyncio.create_task(self.replicate_to_peer(peer))

    async def replicate_to_peer(self, peer):
        """
        Ensure the given follower's log is up to date with the leader's log.
        Implements Raft catch-up replication using nextIndex and matchIndex tracking.
        """
        if isinstance(peer, tuple):
            peer = f"{peer[0]}:{peer[1]}"

        # Initialize follower tracking state
        if peer not in self.next_index:
            self.next_index[peer] = len(self.log)
            self.match_index[peer] = 0
        
        if self.match_index.get(peer, 0) >= len(self.log):
            # Instead of returning silently, send a simple heartbeat
            try:
                async with grpc.aio.insecure_channel(peer) as channel:
                    stub = train_booking_pb2_grpc.RaftStub(channel)
                    prev_log_index = len(self.log)
                    prev_log_term = self.log[-1].term if self.log else 0

                    req = train_booking_pb2.AppendEntriesRequest(
                        term=self.current_term,
                        leader_id=self.node_id,
                        prev_log_index=prev_log_index,
                        prev_log_term=prev_log_term,
                        entries=[],
                        leader_commit=self.commit_index
                    )

                    await stub.AppendEntries(req)
            except Exception:
                print(f"[{self.node_id}] Heartbeat to {peer} failed (peer down?)")
            return

        max_retries = 10
        retries = 0

        while retries < max_retries:
            next_idx = max(0, min(self.next_index.get(peer, len(self.log)), len(self.log)))
            prev_idx = max(0, next_idx - 1)

            # Correct prev_term computation (0-based)
            prev_term = self.log[prev_idx].term if prev_idx < len(self.log) and prev_idx > 0 else 0

            # Determine entries to send
            entries_to_send = self.log[next_idx:] if next_idx < len(self.log) else []

            try:
                async with grpc.aio.insecure_channel(peer) as channel:
                    stub = train_booking_pb2_grpc.RaftStub(channel)

                    req = train_booking_pb2.AppendEntriesRequest(
                        term=self.current_term,
                        leader_id=self.node_id,
                        prev_log_index=prev_idx,
                        prev_log_term=prev_term,
                        entries=[
                            train_booking_pb2.LogEntry(command=e.command, term=e.term)
                            for e in entries_to_send
                        ],
                        leader_commit=self.commit_index,
                    )

                    resp = await stub.AppendEntries(req)

                    # Successful append
                    if getattr(resp, "success", False):
                        self.match_index[peer] = len(self.log)
                        self.next_index[peer] = len(self.log)
                        print(f"[{self.node_id}] {peer} caught up successfully.")
                        return

                    # Follower rejected — decrement next_index and retry
                    self.next_index[peer] = max(0, self.next_index.get(peer, len(self.log)) - 1)
                    retries += 1
                    print(
                        f"[{self.node_id}] {peer} log mismatch, backoff next_index={self.next_index[peer]} (retry {retries})"
                    )

                    # Small delay to avoid spamming
                    await asyncio.sleep(0.2)

            except Exception:
                print(f"[{self.node_id}] Replication to {peer} failed (peer down?)")
                return

        print(f"[{self.node_id}] {peer} failed to catch up after {max_retries} retries.")

    async def append_entries_to_peer(self, peer, entries=None, start_index=None):
        """
        Send one or more log entries (for replication or catch-up).
        - peer: "host:port" or (host, port)
        - entries: optional list of protobuf LogEntry to send (if None, will send entries after commit_index)
        - start_index: optional integer (number of entries before these entries), default computed
        Returns AppendEntriesResponse or None on error.
        """
        if isinstance(peer, tuple):
            peer = f"{peer[0]}:{peer[1]}"

        try:
            # Determine what entries to send
            if entries is None:
                # send everything after commit_index (0-based slice)
                start_index = int(self.commit_index)
                entries_to_send = self.log[start_index:]
            else:
                # entries provided (likely protobuf LogEntry list)
                # compute start_index such that entries correspond to tail of self.log if they were appended
                # If entries were constructed externally, caller should prefer passing start_index too.
                entries_to_send = entries
                if start_index is None:
                    start_index = max(0, len(self.log) - len(entries_to_send))

            prev_log_index = int(start_index)  # number of entries before these entries
            prev_log_term = int(self.log[prev_log_index - 1].term) if prev_log_index > 0 and prev_log_index - 1 < len(self.log) else 0

            async with grpc.aio.insecure_channel(peer) as channel:
                stub = train_booking_pb2_grpc.RaftStub(channel)
                req = train_booking_pb2.AppendEntriesRequest(
                    term=int(self.current_term),
                    leader_id=str(self.node_id),
                    prev_log_index=prev_log_index,
                    prev_log_term=prev_log_term,
                    entries=[train_booking_pb2.LogEntry(command=e.command, term=int(e.term)) for e in entries_to_send],
                    leader_commit=int(self.commit_index)
                )
                resp = await stub.AppendEntries(req)
                return resp
        except Exception as e:
            # print(f"[{self.node_id}] AppendEntries to {peer} failed: {e}")
            print(f"[{self.node_id}] AppendEntries to {peer} failed: Server may be down.")
            return None

    async def handle_client_command(self, command: str):
        """
        Handles a new client command (like 'ADD_TRAIN:...').
        Only the leader should execute this.
        Returns (success: bool, message: str)
        """
        if self.state != "leader":
            print(f"[{self.node_id}] Rejected client command — not the leader.")
            return False, f"Not the leader. Leader: {self.leader_id or 'unknown'}"

        # Create new protobuf LogEntry and append to local log
        new_entry = train_booking_pb2.LogEntry(command=command, term=int(self.current_term))
        self.log.append(new_entry)
        # persist state immediately
        self.save_state()

        # Replicate to followers
        success_count = 1  # leader counts itself
        tasks = []
        for peer in self.peers:
            # send only the new entry; append_entries_to_peer will compute start_index if needed
            tasks.append(self.append_entries_to_peer(peer, entries=[new_entry]))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, train_booking_pb2.AppendEntriesResponse) and r.success:
                success_count += 1

        # Check majority
        if success_count >= (len(self.peers) + 1) // 2:
            # commit this entry (number of entries committed = len(self.log))
            self.commit_index = len(self.log)
            print(f"[{self.node_id}] Log entry committed: {command}")

            # Apply committed entries to local DB (apply only newly committed)
            # if self.last_applied < self.commit_index:
            #     await self.apply_log_entries()
            return True, "Committed"
        else:
            print(f"[{self.node_id}] Failed to commit command: {command}")
            return False, "Commit failed"


    # ------------------------
    # Apply committed entries
    # ------------------------
    async def apply_log_entries(self):
        """
        Apply all committed but not yet applied entries to the local DB.
        This runs asynchronously (spawned when AppendEntries arrives or commit_index changes).
        """

        # Apply entries from last_applied (count) up to commit_index (count)
        if self.applying:
            # already running in background; don't start again
            return

        self.applying = True
        try:
            async with self.apply_lock:
                while self.last_applied < self.commit_index:
                    entry = self.log[self.last_applied]
                    try:
                        await self.apply_log_entry(entry)
                        self.last_applied += 1
                    except Exception as e:
                        # retry safely if SQLite is busy
                        if "database is locked" in str(e).lower():
                            print(f"[{self.node_id}] SQLite busy, retrying in 0.2s...")
                            await asyncio.sleep(0.2)
                            continue
                        print(f"[{self.node_id}] Failed to apply log entry: {e}")
                        break
                    await asyncio.sleep(0.05)  # small yield to let asyncio breathe
        finally:
            self.applying = False

    async def apply_log_entry(self, log_entry):
        """
        Apply a single committed log entry to the local SQLite database.
        Commands follow the format:
          - ADD_TRAIN:train_no,train_name,src_id,dst_id,train_type
          - ADD_SERVICE:train_no,dep,arr,seat_type,seats,price
          - BOOK_SEATS:user_id,service_id,seats
          - CONFIRM_PAYMENT:booking_id,payment_mode
        """
        from database import models as db_models  # avoid circular import

        command = (log_entry.command or "").strip()
        print(f"[{self.node_id}] Applying command: {command}")

        try:
            async with self.db_lock:
                # -------------------------------
                # REGISTER
                # -------------------------------
                if command.startswith("REGISTER:"):
                    # e.g. REGISTER:alice,$2b$12$xyz123,ADMIN
                    payload = command.split(":", 1)[1]
                    parts = [p.strip() for p in payload.split(",")]
                    if len(parts) >= 3:
                        username = parts[0]
                        hashed_password = parts[1].encode("utf-8")
                        await db_models.create_user(username, hashed_password)
                        print(f"[{self.node_id}] User '{username}' registered via Raft log.")
                    else:
                        print(f"[{self.node_id}] Malformed REGISTER command: {payload}")
                
                # -------------------------------
                # LOGIN
                # -------------------------------
                elif command.startswith("CREATE_SESSION:"):
                    parts = command.split(":", 1)[1].split(",")
                    if len(parts) >= 3:
                        user_id = int(parts[0])
                        token = parts[1]
                        expires_at = float(parts[2])
                        await db_models.create_session(user_id, token, expires_at)
                        print(f"[{self.node_id}] Login Session Token created via Raft log.")
                    else:
                        print(f"[{self.node_id}] Malformed Login Session Token command: {payload}")

                # -------------------------------
                # ADD_TRAIN
                # -------------------------------
                elif command.startswith("ADD_TRAIN:"):
                    payload = command.split(":", 1)[1]
                    parts = [p.strip() for p in payload.split(",")]
                    if len(parts) >= 5:
                        train_number = int(parts[0])
                        train_name = parts[1]
                        src = int(parts[2])
                        dst = int(parts[3])
                        train_type = parts[4]
                        await db_models.add_train(train_number, train_name, src, dst, train_type)
                        print(f"[{self.node_id}] Train added via Raft log.")
                    else:
                        print(f"[{self.node_id}] Malformed ADD_TRAIN command: {payload}")

                # -------------------------------
                # ADD_SERVICE
                # -------------------------------
                elif command.startswith("ADD_SERVICE:"):
                    # e.g. ADD_SERVICE:101,2025-11-10 12:00,2025-11-10 18:00,AC2,120,750
                    payload = command.split(":", 1)[1]
                    parts = [p.strip() for p in payload.split(",")]
                    if len(parts) >= 6:
                        train_number = int(parts[0])
                        datetime_of_departure = parts[1]
                        datetime_of_arrival = parts[2]
                        seat_type = parts[3]
                        seats_available = int(parts[4])
                        price = float(parts[5])

                        seat_info_list = [{
                            "seat_type": seat_type,
                            "seats_available": seats_available,
                            "price": price
                        }]

                        await db_models.add_train_service(
                            train_number,
                            datetime_of_departure,
                            datetime_of_arrival,
                            seat_info_list
                        )
                        print(f"[{self.node_id}] Train service added via Raft log.")
                    else:
                        print(f"[{self.node_id}] Malformed ADD_SERVICE command: {payload}")

                # -------------------------------
                # BOOK_SEATS
                # -------------------------------
                elif command.startswith("BOOK_SEATS:"):
                    # e.g. BOOK_SEATS:4,svc_20251108A,3
                    payload = command.split(":", 1)[1]
                    parts = [p.strip() for p in payload.split(",")]
                    if len(parts) >= 3:
                        user_id = int(parts[0])
                        service_id = parts[1]
                        seats = int(parts[2])
                        await db_models.initiate_booking_tx(user_id, service_id, seats)
                        print(f"[{self.node_id}] Booking created via Raft log.")
                    else:
                        print(f"[{self.node_id}] Malformed BOOK_SEATS command: {payload}")

                # -------------------------------
                # CONFIRM_PAYMENT
                # -------------------------------
                elif command.startswith("CONFIRM_PAYMENT:"):
                    # e.g. CONFIRM_PAYMENT:bk_93847,UPI
                    payload = command.split(":", 1)[1]
                    parts = [p.strip() for p in payload.split(",")]
                    if len(parts) >= 2:
                        booking_id = parts[0]
                        payment_mode = parts[1]
                        await db_models.confirm_payment_tx(booking_id, payment_mode)
                        print(f"[{self.node_id}] Payment confirmed via Raft log.")
                    else:
                        print(f"[{self.node_id}] Malformed CONFIRM_PAYMENT command: {payload}")

                else:
                    print(f"[{self.node_id}] Unknown command (no-op): {command}")
            self.save_state()

        except Exception as e:
            print(f"[{self.node_id}] Failed to apply log entry: {e}")