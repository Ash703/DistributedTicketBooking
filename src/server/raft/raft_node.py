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
        self.peers = peers  
        self.state = "follower"
        self.current_term = 0
        self.voted_for = None
        self.log: list[RaftLogEntry] = []
        self.commit_index = 0
        self.last_applied = 0
        self.leader_id = None
        self.db_lock = asyncio.Lock()
        self.apply_lock = asyncio.Lock()
        self.applying = False
        self.heartbeat_received = asyncio.Event()
        self.running = True
        self._background_tasks: list[asyncio.Task] = []
        self.next_index = {peer: 0 for peer in self.peers}
        self.match_index = {peer: 0 for peer in self.peers}

        self.state_file = f"raft_state_node{self.node_id}.json"
        self.load_state()

    async def start(self):
        self._background_tasks.append(asyncio.create_task(self.election_timer()))
        self._background_tasks.append(asyncio.create_task(self.heartbeat_loop()))
        print(f"[{self.node_id}] Raft background tasks started.")
        
    async def stop(self):
        """Gracefully stops all background tasks."""
        print(f"[{self.node_id}] Stopping Raft background tasks...")
        self.running = False
        for task in self._background_tasks:
            task.cancel()
        await asyncio.gather(*self._background_tasks, return_exceptions=True)
        print(f"[{self.node_id}] Raft tasks stopped.")

    def load_state(self):
        """Load Raft term, vote, and log from disk."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                    self.current_term = data.get("current_term", 0)
                    self.voted_for = data.get("voted_for")
                    self.log = [
                        RaftLogEntry(command=e["command"], term=e["term"])
                        for e in data.get("log", [])
                    ]
                    self.last_applied = data.get("last_applied_index", 0)
                print(f"[{self.node_id}] Loaded state: term={self.current_term}, log_len={len(self.log)}")
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
            
            timeout = random.uniform(3.0, 6.0) + random.random() * int(self.node_id)
            try:
                await asyncio.wait_for(self.heartbeat_received.wait(), timeout)
                self.heartbeat_received.clear()
            except asyncio.TimeoutError:
                if self.running: 
                    print(f"[{self.node_id}] Election timeout. Starting election.")
                    await self.start_election()
            except asyncio.CancelledError:
                break 

    async def start_election(self):
        """Initiate an election for leadership."""
        self.state = "candidate"
        self.current_term += 1
        self.voted_for = self.node_id
        self.save_state()
        votes = 1
        self.heartbeat_received.clear()
        
        tasks = [self.request_vote_from_peer(peer) for peer in self.peers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, train_booking_pb2.VoteResponse) and r.vote_granted:
                votes += 1

        if not self.running or self.state != "candidate":
            return 

        if votes > (len(self.peers) + 1) // 2:
            print(f"[{self.node_id}] Became leader (term {self.current_term})")
            self.state = "leader"
            self.leader_id = f"localhost:{50050 + int(self.node_id)}" 
            self.heartbeat_received.clear()
            
            log_len = len(self.log)
            for peer in self.peers:
                peer_str = f"{peer[0]}:{peer[1]}" if isinstance(peer, tuple) else peer
                self.next_index[peer_str] = log_len + 1 
                self.match_index[peer_str] = 0
        else:
            self.state = "follower" 
            print(f"[{self.node_id}] Election failed with {votes} votes.")

    async def request_vote_from_peer(self, peer):
        if isinstance(peer, tuple):
            peer = f"{peer[0]}:{peer[1]}"
        
        last_log_index = len(self.log)
        last_log_term = self.log[last_log_index - 1].term if last_log_index > 0 else 0

        try:
            async with grpc.aio.insecure_channel(peer) as channel:
                stub = train_booking_pb2_grpc.RaftStub(channel)
                req = train_booking_pb2.VoteRequest(
                    term=self.current_term,
                    candidate_id=self.node_id,
                    last_log_index=last_log_index,
                    last_log_term=last_log_term
                )
                return await stub.RequestVote(req)
        except Exception:
            # print(f"[{self.node_id}] Failed to contact {peer}: Server may be down.")
            return None
    
    async def RequestVote(self, request, context):
        """Handle incoming vote requests."""
        if request.term < self.current_term:
            return train_booking_pb2.VoteResponse(term=self.current_term, vote_granted=False)
        
        if request.term > self.current_term:
            self.current_term = int(request.term)
            self.voted_for = None
            self.state = "follower"
            self.save_state()

        last_log_index = len(self.log)
        last_log_term = self.log[last_log_index - 1].term if last_log_index > 0 else 0
        
        # Raft Safety Property 5.4.1:
        log_ok = (request.last_log_term > last_log_term) or \
                 (request.last_log_term == last_log_term and request.last_log_index >= last_log_index)

        if (self.voted_for is None or self.voted_for == request.candidate_id) and log_ok:
            self.voted_for = request.candidate_id
            self.current_term = int(request.term)
            self.state = "follower"
            self.save_state()
            self.heartbeat_received.set() 
            print(f"[{self.node_id}] Voted for {request.candidate_id} (term {request.term})")
            return train_booking_pb2.VoteResponse(term=self.current_term, vote_granted=True)

        return train_booking_pb2.VoteResponse(term=self.current_term, vote_granted=False)
    
    async def AppendEntries(self, request, context):
        """Handle heartbeat and log replication."""
        if request.term < self.current_term:
            return train_booking_pb2.AppendEntriesResponse(term=self.current_term, success=False)
        
        
        self.heartbeat_received.set()
        self.state = "follower"
        self.current_term = request.term
        self.leader_id = request.leader_id
        self.voted_for = None
        self.save_state()
        prev_log_index = int(request.prev_log_index)
        prev_log_term = int(request.prev_log_term)
        if prev_log_index > len(self.log):
            return train_booking_pb2.AppendEntriesResponse(term=self.current_term, success=False)
        if prev_log_index > 0:
            if prev_log_index - 1 >= len(self.log):
                 return train_booking_pb2.AppendEntriesResponse(term=self.current_term, success=False)
                 
            if self.log[prev_log_index - 1].term != prev_log_term:
                self.log = self.log[:prev_log_index - 1]
                self.save_state()
                return train_booking_pb2.AppendEntriesResponse(term=self.current_term, success=False)
        idx = prev_log_index
        for incoming in request.entries:
            entry = RaftLogEntry(command=incoming.command, term=incoming.term)
            if idx < len(self.log):
                if self.log[idx].term != incoming.term:
                    self.log = self.log[:idx] 
                    self.log.append(entry)
            else:
                self.log.append(entry)
            idx += 1
        leader_commit = int(request.leader_commit)
        if leader_commit > self.commit_index:
            self.commit_index = min(leader_commit, len(self.log))
            
        self.save_state() 
        if self.commit_index > self.last_applied:
            asyncio.create_task(self.apply_log_entries())

        return train_booking_pb2.AppendEntriesResponse(term=self.current_term, success=True)

    async def heartbeat_loop(self):
        """Leaders send heartbeats periodically."""
        while self.running:
            if self.state == "leader":
                await self.send_heartbeats()
            try:
                await asyncio.sleep(2.0)
            except asyncio.CancelledError:
                break

    async def send_heartbeats(self):
        """Send AppendEntries RPCs to all peers."""
        for peer in self.peers:
            asyncio.create_task(self.append_entries_to_peer(peer))

    async def append_entries_to_peer(self, peer, entries=None):
        """
        Sends entries based on next_index, or specific entries if provided.
        This handles both heartbeats and replication.
        """
        if self.state != "leader" or not self.running:
            return False

        if isinstance(peer, tuple):
            peer = f"{peer[0]}:{peer[1]}"
            
        if peer not in self.next_index:
             self.next_index[peer] = len(self.log) + 1
        next_idx_1_based = self.next_index[peer]
        prev_log_index = max(0, next_idx_1_based - 1)
        entries_to_send = entries if entries is not None else self.log[prev_log_index:]
        prev_log_term = self.log[prev_log_index - 1].term if prev_log_index > 0 else 0

        try:
            async with grpc.aio.insecure_channel(peer) as channel:
                stub = train_booking_pb2_grpc.RaftStub(channel)
                req = train_booking_pb2.AppendEntriesRequest(
                    term=int(self.current_term),
                    leader_id=self.node_id,
                    prev_log_index=prev_log_index,
                    prev_log_term=prev_log_term,
                    entries=[train_booking_pb2.LogEntry(command=e.command, term=int(e.term)) for e in entries_to_send],
                    leader_commit=int(self.commit_index)
                )
                
                resp = await stub.AppendEntries(req)
                
                if resp:
                    if resp.success:
                        new_match_index = prev_log_index + len(entries_to_send)
                        self.match_index[peer] = max(self.match_index.get(peer, 0), new_match_index)
                        self.next_index[peer] = self.match_index[peer] + 1
                        if entries_to_send:
                            await self.update_leader_commit_index()
                        return True
                    else:
                        if resp.term > self.current_term:
                            self.state = "follower"
                            self.current_term = resp.term
                            self.voted_for = None
                            self.save_state()
                        else:
                            self.next_index[peer] = max(1, self.next_index[peer] - 1)
                        return False
        except Exception:
            # print(f"[{self.node_id}] AppendEntries to {peer} failed (peer down?)")
            return False
        return False
    
    async def update_leader_commit_index(self):
        """Checks if a majority of followers have replicated, and updates commit_index."""
        if self.state != "leader":
            return
        majority_count = (len(self.peers) // 2) + 1
        
        matches = [self.match_index[peer] for peer in self.peers] + [len(self.log)]
        matches.sort(reverse=True)
        new_commit_index = matches[majority_count - 1]
        if new_commit_index > self.commit_index and \
           new_commit_index > 0 and \
           new_commit_index <= len(self.log) and \
           self.log[new_commit_index - 1].term == self.current_term:
            
            self.commit_index = new_commit_index
            print(f"[{self.node_id}] Leader commit index updated to {self.commit_index}")
            if self.last_applied < self.commit_index:
                asyncio.create_task(self.apply_log_entries())

    async def handle_client_command(self, command: str):
        """
        Handles a new command from the BookingService.
        This is the "Log-First" logic.
        """
        if self.state != "leader":
            leader_port = "unknown"
            if self.leader_id:
                leader_port = self.leader_id.split(':')[-1]
            return False, f"Not the leader. Please contact leader {leader_port}"
        new_entry = RaftLogEntry(command=command, term=int(self.current_term))
        self.log.append(new_entry)
        self.save_state()
        success_count = 1
        tasks = []
        for peer in self.peers:
            tasks.append(self.append_entries_to_peer(peer, entries=[new_entry]))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if res is True:
                success_count += 1
        if success_count > (len(self.peers) + 1) // 2:
            self.commit_index = len(self.log)
            print(f"[{self.node_id}] Log entry committed.")
            result_msg = await self.apply_log_entries()
            
            return True, result_msg if result_msg else "Committed"
        else:
            self.log.pop() 
            self.save_state()
            print(f"[{self.node_id}] Failed to commit.")
            return False, "Commit failed: No majority."

    async def apply_log_entries(self):
        """Apply all committed but not yet applied entries to the local DB."""
        if self.applying: 
            return
        self.applying = True
        
        last_result = "Applied"

        try:
            async with self.apply_lock:
                while self.last_applied < self.commit_index:
                    entry_index_to_apply = self.last_applied
                    entry = self.log[entry_index_to_apply]
                    last_result = await self.apply_log_entry(entry)
                    
                    self.last_applied += 1
                self.save_state() 
        finally:
            self.applying = False
        
        return last_result

    async def apply_log_entry(self, log_entry):
        """
        Parses JSON command and applies it to the state machine (database).
        This is the ONLY place database writes should happen.
        """
        from database import models as db_models
        from utils import security as security_utils 

        command_str = (log_entry.command or "").strip()
        print(f"[{self.node_id}] Processing state machine: {command_str[:70]}...")
        
        try:
            data = json.loads(command_str)
            action = data.get("action")
            
            async with self.db_lock:
                if action == "REGISTER":
                    msg = await db_models.create_user(
                        data["username"], 
                        data["hashed_password"].encode("utf-8")
                    )
                    return "User Registered"
                
                elif action == "CREATE_SESSION":
                    await db_models.create_session(
                        data["user_id"], 
                        data["token"], 
                        data["expires_at"]
                    )
                    return "Session Created"

                elif action == "ADD_TRAIN":
                    success = await db_models.add_train(
                        data["train_number"], data["train_name"], 
                        data["source_city_id"], data["destination_city_id"], data["train_type"]
                    )
                    return "Train Added" if success else "Train number already exists."

                elif action == "ADD_SERVICE":
                    await db_models.add_train_service(
                        data["train_number"], data["datetime_of_departure"], 
                        data["datetime_of_arrival"], data["seat_info"]
                    )
                    return "Service Added"

                elif action == "BOOK_SEATS":
                    success, msg, b_id, cost = await db_models.initiate_booking_tx(
                        data["user_id"], data["service_id"], 
                        data["number_of_seats"], 
                        data.get("booking_id"), 
                        data.get("total_cost")  
                    )
                    if success: return f"{b_id},{cost}" 
                    
                    return msg

                elif action == "CONFIRM_PAYMENT":
                    success, msg = await db_models.confirm_payment_tx(
                        data["booking_id"], 
                        data["payment_mode"],
                        data.get("payment_id"),
                        data.get("transaction_id") 
                    )
                    return msg
                
                elif action == "CANCEL_BOOKING":
                    success, msg = await db_models.cancel_booking_tx(
                        data["booking_id"],
                        data["user_id"]
                    )
                    return msg

                else:
                    print(f"[{self.node_id}] Unknown JSON action: {action}")
                    return "Unknown Action"

        except json.JSONDecodeError:
            print(f"[{self.node_id}] Error: Log entry is not valid JSON.")
            return "JSON Error"
        except Exception as e:
            print(f"[{self.node_id}] DB Error applying log: {e}")
            return f"DB Error: {e}"
    