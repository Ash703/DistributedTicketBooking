// --- APP STATE ---
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
        if (!response.ok) {
            const errText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errText}`);
        }
        return await response.json();
    } catch (err) {
        console.error(`Fetch error for ${endpoint}:`, err);
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

// --- CORE LOGIC ---
async function checkLoginState() {
    state.token = sessionStorage.getItem('authToken');
    state.role = sessionStorage.getItem('authRole');
    state.username = sessionStorage.getItem('authUsername');
    
    const userGreeting = document.getElementById('user-greeting');
    const logoutButton = document.getElementById('logout-button');
    const authSection = document.getElementById('auth-section');
    const customerApp = document.getElementById('customer-app');
    const adminApp = document.getElementById('admin-app');
    const mainNav = document.getElementById('main-nav');

    if (state.token && state.role) {
        // Logged In
        userGreeting.textContent = `Hi, ${state.username}`;
        logoutButton.classList.remove('hidden');
        authSection.classList.add('hidden');
        mainNav.classList.remove('hidden');
        
        await loadCities(); // Load cities for dropdowns

        if (state.role === 'CUSTOMER') {
            customerApp.classList.remove('hidden');
            adminApp.classList.add('hidden');
        } else {
            customerApp.classList.add('hidden');
            adminApp.classList.remove('hidden');
        }
    } else {
        // Logged Out
        userGreeting.textContent = 'You are not logged in.';
        logoutButton.classList.add('hidden');
        authSection.classList.remove('hidden');
        mainNav.classList.add('hidden');
        customerApp.classList.add('hidden');
        adminApp.classList.add('hidden');
    }
}

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
                const firstOption = el.options[0];
                el.innerHTML = '';
                el.add(firstOption);
                state.cities.forEach(city => {
                    el.add(new Option(`${city.city_name} (${city.city_code})`, city.city_id));
                });
            }
        });
    }
}

// --- AUTH EVENT LISTENERS ---
document.getElementById('logout-button').addEventListener('click', () => {
    sessionStorage.clear();
    checkLoginState();
});

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
        checkLoginState();
    } else {
        msg.className = 'auth-message error';
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
        msg.className = 'auth-message success';
        msg.textContent = 'Registered! Please log in.';
        e.target.reset();
    } else {
        msg.className = 'auth-message error';
        msg.textContent = resp ? resp.message : "Registration failed";
    }
});

// Auth form toggling
document.getElementById('show-login-btn').addEventListener('click', () => {
    document.getElementById('login-form').classList.remove('hidden');
    document.getElementById('register-form').classList.add('hidden');
    document.getElementById('show-login-btn').classList.add('active');
    document.getElementById('show-register-btn').classList.remove('active');
});
document.getElementById('show-register-btn').addEventListener('click', () => {
    document.getElementById('login-form').classList.add('hidden');
    document.getElementById('register-form').classList.remove('hidden');
    document.getElementById('show-login-btn').classList.remove('active');
    document.getElementById('show-register-btn').classList.add('active');
});

// --- CUSTOMER ACTIONS ---

document.getElementById('search-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const container = document.getElementById('search-results');
    container.innerHTML = '<p class="loading" style="text-align:center;">Searching for trains...</p>';

    const resp = await apiFetch('/api/search', {
        source_city_id: document.getElementById('search-from').value,
        destination_city_id: document.getElementById('search-to').value,
        date: document.getElementById('search-date').value
    });

    if (!resp || resp.length === 0) {
        container.innerHTML = '<p class="placeholder" style="text-align:center;">No trains found for this route and date.</p>';
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
            const availText = cls.seats_available > 0 ? `Available ${cls.seats_available}` : 'Waiting List';
            
            classesHtml += `
                <div class="class-card" onclick="bookTicket('${cls.service_id}')">
                    <div style="display:flex; justify-content: space-between;">
                        <span class="class-name">${cls.seat_type}</span>
                        <span class="class-price">₹${cls.price.toFixed(2)}</span>
                    </div>
                    <span class="${availClass}">${availText}</span>
                    <div class="book-now-hover">Book Now</div>
                </div>
            `;
        });

        html += `
        <div class="train-card">
            <div class="train-header">
                <div class="train-info">
                    <h4>${t.name} <span class="train-number">#${t.number}</span></h4>
                    <div class="train-route">
                        <div class="time-group">
                            <div class="time">${depTime}</div>
                            <div class="city">${t.source}</div>
                        </div>
                        <span class="duration-line"></span>
                        <div class="time-group">
                            <div class="time">${arrTime}</div>
                            <div class="city">${t.dest}</div>
                        </div>
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
    const seats = prompt("How many seats do you want to book?", "1");
    if (!seats || isNaN(parseInt(seats)) || parseInt(seats) <= 0) return;

    const initResp = await apiFetch('/api/initiate_booking', {
        token: state.token, service_id: serviceId, num_seats: parseInt(seats)
    });

    if (!initResp || !initResp.success) {
        alert("Booking Failed: " + (initResp ? initResp.message : "Unknown error"));
        return;
    }

    if (confirm(`Total cost: ₹${initResp.total_cost.toFixed(2)}. Confirm payment?`)) {
        const payResp = await apiFetch('/api/process_payment', {
            token: state.token, booking_id: initResp.booking_id, payment_mode: "Web"
        });
        alert(payResp.message);
        document.getElementById('view-bookings-button').click();
    }
};

document.getElementById('view-bookings-button').addEventListener('click', async () => {
    const div = document.getElementById('bookings-list');
    div.innerHTML = "<p class='loading' style='padding:20px;'>Loading...</p>";
    const resp = await apiFetch('/api/my_bookings', { token: state.token });
    
    if (!resp || resp.length === 0) {
        div.innerHTML = "<p class='placeholder' style='padding:20px;'>No bookings found.</p>";
        return;
    }

    let html = "";
    resp.forEach(b => {
        const btn = (b.status !== 'CANCELLED') ? `<button class="btn-cancel" onclick="cancelBooking('${b.booking_id}')">Cancel</button>` : `<span class="status-badge status-CANCELLED">Cancelled</span>`;
        html += `
            <div class="booking-item">
                <div class="booking-info">
                    <div class="b-train">${b.train_name}</div>
                    <div class="b-route">${b.source} &rarr; ${b.destination}</div>
                    <div class="b-meta">${b.datetime_of_departure} | ${b.number_of_seats} Seats</div>
                </div>
                <div><span class="status-badge status-${b.status}">${b.status}</span></div>
                <div><strong>₹${b.total_cost.toFixed(2)}</strong></div>
                <div>${btn}</div>
            </div>`;
    });
    div.innerHTML = html;
});

window.cancelBooking = async function(bookingId) {
    if (!confirm("Are you sure you want to cancel this booking?")) return;
    const resp = await apiFetch('/api/cancel_booking', { token: state.token, booking_id: bookingId });
    alert(resp.message);
    document.getElementById('view-bookings-button').click();
};

// Chatbot
document.getElementById('chat-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = document.getElementById('chat-input');
    const text = input.value;
    if(!text) return;
    
    const msgs = document.getElementById('chat-messages');
    msgs.innerHTML += `<div class="msg user">${text}</div>`;
    input.value = '';
    
    const botDiv = document.createElement('div');
    botDiv.className = 'msg bot';
    botDiv.innerText = "...";
    msgs.appendChild(botDiv);
    msgs.scrollTop = msgs.scrollHeight;

    try {
        const response = await fetch('/api/ask_bot', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ token: state.token, query: text })
        });
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullText = "";

        while(true) {
            const {value, done} = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value, {stream: true});
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
    } catch(e) { botDiv.innerText = `Error: ${e.message}`; }
});

// --- ADMIN ACTIONS ---
function setAdminMessage(message, isSuccess) {
    const msgEl = document.getElementById('admin-message');
    msgEl.textContent = message;
    msgEl.className = isSuccess ? 'alert success' : 'alert error';
}

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
    setAdminMessage(resp.message, resp.success);
    if(resp.success) e.target.reset();
});

document.getElementById('add-seat-class-btn').addEventListener('click', () => {
    const div = document.createElement('div');
    div.className = "seat-entry";
    div.innerHTML = `
        <select class="seat-type"><option value="AC1">AC1</option><option value="AC2">AC2</option><option value="AC3">AC3</option><option value="GENERAL">GENERAL</option></select>
        <input type="number" class="seat-count" placeholder="Seats" style="width:100px;">
        <input type="number" class="seat-price" placeholder="Price" style="width:100px;">
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

    if(seats.length === 0) {
        setAdminMessage("Please add at least one seat class.", false);
        return;
    }

    const depInput = document.getElementById('admin-service-departure').value;
    const arrInput = document.getElementById('admin-service-arrival').value;

    const resp = await apiFetch('/api/admin/add_service', {
        token: state.token,
        train_number: document.getElementById('admin-service-train-num').value,
        datetime_of_departure: formatDateTimeForServer(depInput),
        datetime_of_arrival: formatDateTimeForServer(arrInput),
        seat_info: seats
    });
    setAdminMessage(resp.message, resp.success);
    if(resp.success) { 
        e.target.reset(); 
        document.getElementById('seat-classes-container').innerHTML = ''; 
    }
});

async function fetchAdminTrains(sId, dId) {
    const div = document.getElementById('admin-trains-list');
    div.innerHTML = "<p class='loading'>Loading routes...</p>";
    const resp = await apiFetch('/api/admin/view_trains', {
        token: state.token,
        source_city_id: sId,
        destination_city_id: dId
    });

    if (!resp || resp.length === 0) {
        div.innerHTML = '<p class="placeholder">No trains found.</p>';
        return;
    }

    let table = '<table><tr><th>Number</th><th>Name</th><th>Type</th><th>From</th><th>To</th></tr>';
    resp.forEach(t => {
        table += `<tr>
            <td>${t.number}</td>
            <td><strong>${t.name}</strong></td>
            <td>${t.type}</td>
            <td>${t.source}</td>
            <td>${t.destination}</td>
        </tr>`;
    });
    table += '</table>';
    div.innerHTML = table;
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
    fetchAdminTrains(0, 0);
});

// --- Initial Page Load ---
document.addEventListener('DOMContentLoaded', checkLoginState);