// --- STATE ---
const state = { token: null, role: null, username: null, cities: [] };

// --- API HELPER ---
async function apiFetch(endpoint, body) {
    try {
        const options = {
            method: body ? 'POST' : 'GET',
            headers: { 'Content-Type': 'application/json' },
            body: body ? JSON.stringify(body) : null
        };
        const response = await fetch(endpoint, options);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (err) {
        console.error(err);
        return null;
    }
}

// --- HELPER: Date Formatter ---
function formatDateTimeForServer(datetimeInput) {
    if (!datetimeInput) return "";
    return datetimeInput.replace("T", " ") + ":00";
}

function formatTimeDisplay(datetimeStr) {
    if(!datetimeStr) return "";
    const parts = datetimeStr.split(' ');
    if(parts.length > 1) {
        return parts[1].substring(0, 5); 
    }
    return datetimeStr;
}

// --- UI MANAGEMENT ---
function updateUI() {
    state.token = sessionStorage.getItem('authToken');
    state.role = sessionStorage.getItem('authRole');
    state.username = sessionStorage.getItem('authUsername');

    const mainNav = document.getElementById('main-nav');
    const authSection = document.getElementById('auth-section');
    const customerApp = document.getElementById('customer-app');
    const adminApp = document.getElementById('admin-app');
    const userGreeting = document.getElementById('user-greeting');

    if (state.token) {
        mainNav.classList.remove('hidden');
        authSection.classList.add('hidden');
        userGreeting.textContent = `Hi, ${state.username}`;
        
        loadCities(); 

        if (state.role === 'CUSTOMER') {
            customerApp.classList.remove('hidden');
            adminApp.classList.add('hidden');
        } else {
            customerApp.classList.add('hidden');
            adminApp.classList.remove('hidden');
        }
    } else {
        mainNav.classList.add('hidden');
        authSection.classList.remove('hidden');
        customerApp.classList.add('hidden');
        adminApp.classList.add('hidden');
    }
}

// --- LOAD CITIES (Fixed for Admin Filters) ---
async function loadCities() {
    const resp = await apiFetch('/api/cities');
    if (resp) {
        state.cities = resp;
        const dropdowns = [
            'search-from', 'search-to', 
            'admin-from-city', 'admin-to-city',
            'admin-filter-from', 'admin-filter-to'
        ];
        
        dropdowns.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                // FIX: Explicitly set the default option instead of cloning
                el.innerHTML = '<option value="">Select City...</option>';
                
                state.cities.forEach(city => {
                    el.add(new Option(`${city.city_name} (${city.city_code})`, city.city_id));
                });
            }
        });
    }
}
// --- AUTH EVENTS ---
document.getElementById('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const u = document.getElementById('login-username').value;
    const p = document.getElementById('login-password').value;
    const msg = document.getElementById('login-message');
    msg.textContent = "Logging in...";
    const resp = await apiFetch('/api/login', { username: u, password: p });
    if (resp && resp.success) {
        sessionStorage.setItem('authToken', resp.token);
        sessionStorage.setItem('authRole', resp.role);
        sessionStorage.setItem('authUsername', u);
        updateUI();
    } else {
        msg.textContent = resp ? resp.message : "Login failed";
    }
});

document.getElementById('register-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const u = document.getElementById('register-username').value;
    const p = document.getElementById('register-password').value;
    const msg = document.getElementById('register-message');
    msg.textContent = "Registering...";
    const resp = await apiFetch('/api/register', { username: u, password: p });
    if (resp && resp.success) {
        msg.textContent = "Success! Switch to Login.";
        msg.className = "mb-0 mt-4 text-center success-text";
    } else {
        msg.textContent = resp ? resp.message : "Failed";
    }
});

document.getElementById('logout-button').addEventListener('click', () => {
    sessionStorage.clear();
    updateUI();
});

// --- CUSTOMER: SEARCH & BOOK (GROUPED UI) ---
document.getElementById('search-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const container = document.getElementById('search-results');
    container.innerHTML = '<p style="color:#333; text-align:center;">Searching...</p>';

    const resp = await apiFetch('/api/search', {
        source_city_id: document.getElementById('search-from').value,
        destination_city_id: document.getElementById('search-to').value,
        date: document.getElementById('search-date').value
    });

    if (!resp || resp.length === 0) {
        container.innerHTML = '<p style="color:#333; text-align:center;">No trains found.</p>';
        return;
    }

    const trains = {};
    resp.forEach(s => {
        if (!trains[s.train_name]) {
            trains[s.train_name] = {
                number: s.train_number || "",
                name: s.train_name,
                dep: s.datetime_of_departure,
                arr: s.datetime_of_arrival,
                source: s.source_city_name,
                dest: s.destination_city_name,
                classes: []
            };
        }
        trains[s.train_name].classes.push(s);
    });

    let html = '';
    for (const [name, t] of Object.entries(trains)) {
        const depTime = formatTimeDisplay(t.dep);
        const arrTime = formatTimeDisplay(t.arr);

        let classesHtml = '';
        t.classes.forEach(cls => {
            const availClass = cls.seats_available > 10 ? 'class-avail' : 'class-avail low';
            const availText = cls.seats_available > 0 ? `Available ${cls.seats_available}` : 'WL';
            
            classesHtml += `
                <div class="class-card" onclick="bookTicket('${cls.service_id}')">
                    <div class="d-flex justify-content-between">
                        <span class="class-name">${cls.seat_type}</span>
                        <span class="class-price">₹${cls.price}</span>
                    </div>
                    <div class="${availClass}">${availText}</div>
                    <button class="book-btn-overlay">Book</button>
                </div>
            `;
        });

        html += `
        <div class="train-card">
            <div class="train-header">
                <div class="train-title">${t.name} <span style="font-weight:400; font-size:14px; color:#666;">#${t.number}</span></div>
                <div class="train-meta">
                    <div style="text-align:center;">
                        <div class="train-time">${depTime}</div>
                        <div style="font-size:12px; color:#666;">${t.source}</div>
                    </div>
                    <div style="text-align:center; padding-top:5px;">
                        <div style="font-size:12px; color:#888;">--- view route ---</div>
                    </div>
                    <div style="text-align:center;">
                        <div class="train-time">${arrTime}</div>
                        <div style="font-size:12px; color:#666;">${t.dest}</div>
                    </div>
                </div>
            </div>
            <div class="class-container">
                ${classesHtml}
            </div>
        </div>`;
    }
    container.innerHTML = html;
});

window.bookTicket = async function(serviceId) {
    const seats = prompt("Number of seats:", "1");
    if(!seats) return;
    
    const initResp = await apiFetch('/api/initiate_booking', {
        token: state.token, service_id: serviceId, num_seats: parseInt(seats)
    });

    if(!initResp || !initResp.success) {
        alert("Failed: " + (initResp ? initResp.message : "Error"));
        return;
    }

    if(confirm(`Total: ₹${initResp.total_cost}. Pay now?`)) {
        const payResp = await apiFetch('/api/process_payment', {
            token: state.token, booking_id: initResp.booking_id, payment_mode: "Web"
        });
        alert(payResp.message);
        document.getElementById('view-bookings-button').click();
    }
};

// --- CUSTOMER: MY BOOKINGS ---
document.getElementById('view-bookings-button').addEventListener('click', async () => {
    const div = document.getElementById('bookings-list');
    div.innerHTML = "Loading...";
    const resp = await apiFetch('/api/my_bookings', { token: state.token });
    if(!resp || resp.length === 0) {
        div.innerHTML = "<p style='color:#888'>No bookings found.</p>";
        return;
    }
    let html = "<table><tr><th>Train</th><th>Date</th><th>Seats</th><th>Status</th><th>Action</th></tr>";
    resp.forEach(b => {
        const btn = b.status !== 'CANCELLED' ? `<button class="btn-text" style="color:#ff7675;" onclick="cancelBooking('${b.booking_id}')">Cancel</button>` : '<span style="color:#aaa">Cancelled</span>';
        html += `<tr><td>${b.train_name}</td><td>${b.datetime_of_departure}</td><td>${b.number_of_seats}</td><td>${b.status}</td><td>${btn}</td></tr>`;
    });
    div.innerHTML = html + "</table>";
});

window.cancelBooking = async function(bid) {
    if(!confirm("Cancel booking?")) return;
    await apiFetch('/api/cancel_booking', {token: state.token, booking_id: bid});
    document.getElementById('view-bookings-button').click();
};

// --- CHATBOT ---
document.getElementById('chat-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = document.getElementById('chat-input');
    const text = input.value;
    if(!text) return;
    
    const msgs = document.getElementById('chat-messages');
    msgs.innerHTML += `<div class="user-msg">${text}</div>`;
    input.value = '';
    
    const botDiv = document.createElement('div');
    botDiv.className = 'bot-msg';
    botDiv.innerText = "...";
    msgs.appendChild(botDiv);
    msgs.scrollTop = msgs.scrollHeight;

    try {
        const response = await fetch('/api/ask_bot', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ token: state.token, query: text })
        });
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullText = "";
        while(true) {
            const {value, done} = await reader.read();
            if(done) break;
            const chunk = decoder.decode(value, {stream:true});
            const lines = chunk.split('\n');
            for(const line of lines) {
                if(line.startsWith('data: ')) {
                    const dataStr = line.substring(6);
                    if(dataStr.includes('[STREAM_END]')) break;
                    try {
                        const json = JSON.parse(dataStr);
                        if(fullText === "") botDiv.innerText = "";
                        fullText += json.answer;
                        botDiv.innerText = fullText;
                        msgs.scrollTop = msgs.scrollHeight;
                    } catch(e){}
                }
            }
        }
    } catch(e) { botDiv.innerText = "Error."; }
});

// --- ADMIN FUNCTIONS ---
document.getElementById('add-train-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const resp = await apiFetch('/api/admin/add_train', {
        token: state.token,
        train_number: document.getElementById('admin-train-num').value,
        train_name: document.getElementById('admin-train-name').value,
        source_city_id: document.getElementById('admin-from-city').value,
        destination_city_id: document.getElementById('admin-to-city').value,
        train_type: document.getElementById('admin-train-type').value
    });
    document.getElementById('admin-message').textContent = resp.message;
    if(resp.success) e.target.reset();
});

document.getElementById('add-seat-class-btn').addEventListener('click', () => {
    const div = document.createElement('div');
    div.className = "row mb-2 seat-entry";
    div.innerHTML = `
        <div class="col-4"><select class="form-style-light seat-type"><option value="AC1">AC1</option><option value="AC2">AC2</option><option value="AC3">AC3</option><option value="GENERAL">SL/Gen</option></select></div>
        <div class="col-4"><input type="number" class="form-style-light seat-count" placeholder="Seats"></div>
        <div class="col-4"><input type="number" class="form-style-light seat-price" placeholder="Price"></div>
    `;
    document.getElementById('seat-classes-container').appendChild(div);
});

document.getElementById('add-service-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const seats = [];
    document.querySelectorAll('.seat-entry').forEach(div => {
        seats.push({
            seat_type: div.querySelector('.seat-type').value,
            seats_available: div.querySelector('.seat-count').value,
            price: div.querySelector('.seat-price').value
        });
    });

    const depInput = document.getElementById('admin-service-departure').value;
    const arrInput = document.getElementById('admin-service-arrival').value;

    const resp = await apiFetch('/api/admin/add_service', {
        token: state.token,
        train_number: document.getElementById('admin-service-train-num').value,
        datetime_of_departure: formatDateTimeForServer(depInput),
        datetime_of_arrival: formatDateTimeForServer(arrInput),
        seat_info: seats
    });
    document.getElementById('admin-message').textContent = resp.message;
    if(resp.success) { e.target.reset(); document.getElementById('seat-classes-container').innerHTML = ''; }
});

// --- ADMIN VIEW ALL LOGIC ---
async function fetchAdminTrains(sId, dId) {
    const div = document.getElementById('admin-trains-list');
    div.innerHTML = "Loading...";
    const resp = await apiFetch('/api/admin/view_trains', {token: state.token, source_city_id: sId, destination_city_id: dId});
    if(!resp || resp.length==0) { div.innerHTML="<p>No trains found.</p>"; return; }
    let html = "<table class='table table-sm'><tr><th>No</th><th>Name</th><th>Type</th><th>From</th><th>To</th></tr>";
    resp.forEach(t => html+=`<tr><td>${t.number}</td><td>${t.name}</td><td>${t.type}</td><td>${t.source}</td><td>${t.destination}</td></tr>`);
    div.innerHTML = html + "</table>";
}

document.getElementById('admin-view-trains-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const s = document.getElementById('admin-filter-from').value;
    const d = document.getElementById('admin-filter-to').value;
    fetchAdminTrains(s || 0, d || 0);
});

document.getElementById('admin-view-all-btn').addEventListener('click', () => {
    document.getElementById('admin-filter-from').value = "";
    document.getElementById('admin-filter-to').value = "";
    fetchAdminTrains(0,0);
});

// Init
updateUI();