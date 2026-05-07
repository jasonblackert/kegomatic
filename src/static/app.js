// Kegomatic Web UI - JavaScript Client
// WebSocket client with real-time updates and animations

// Initialize Socket.IO connection
const socket = io();

// Configuration
const config = {
    kegs: {}
};

// State tracking
let connectionStatus = 'disconnected';
let pourPopupTimeout = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    console.log('Kegomatic UI initializing...');
    initializeUI();
    setupSocketListeners();
    fetchInitialConfig();
});

// Initialize UI elements
function initializeUI() {
    // Set initial time/date
    updateTime();
    setInterval(updateTime, 1000);
}

// Fetch initial configuration from REST API
async function fetchInitialConfig() {
    try {
        const response = await fetch('/api/config');
        const data = await response.json();
        config.kegs = data.kegs || {};
        console.log('Config loaded:', config);
        populateKegInfo();
    } catch (error) {
        console.error('Error fetching config:', error);
    }
}

// Populate static keg information
function populateKegInfo() {
    Object.entries(config.kegs).forEach(([kegNum, kegData]) => {
        const id = kegNum;

        // Set beer info
        setElementText(`name-${id}`, kegData.name || 'Unknown');
        setElementText(`brewery-${id}`, kegData.brewery || '---');
        setElementText(`type-${id}`, kegData.type || '---');
        setElementText(`abv-${id}`, kegData.abv ? `${kegData.abv}%` : 'n/a');
        setElementText(`ibu-${id}`, kegData.ibu || 'n/a');

        // Set brewery logo
        const logoImg = document.getElementById(`logo-${id}`);
        if (logoImg && kegData.logo) {
            logoImg.src = `/logos/${kegData.logo}`;
            logoImg.alt = kegData.brewery || 'Brewery Logo';
        }
    });
}

// Socket.IO Event Listeners
function setupSocketListeners() {
    // Connection events
    socket.on('connect', () => {
        console.log('✓ Connected to server');
        connectionStatus = 'connected';
    });

    socket.on('disconnect', () => {
        console.log('✗ Disconnected from server');
        connectionStatus = 'disconnected';
    });

    socket.on('connect_error', (error) => {
        console.error('Connection error:', error);
    });

    // Config event
    socket.on('config', (data) => {
        console.log('Received config:', data);
        config.kegs = data.kegs || {};
        populateKegInfo();
    });

    // Keg update event
    socket.on('keg_update', (data) => {
        const { keg_id, data: kegData } = data;
        updateKegDisplay(keg_id, kegData);
    });

    // Temperature update
    socket.on('temp_update', (data) => {
        if (data.TempF !== undefined) {
            animateNumber('keg-temp', data.TempF, 1);
        }
    });

    // TV status update
    socket.on('tv_status', (data) => {
        if (data.SleepTimer !== undefined) {
            setElementText('tv-sleep', data.SleepTimer);
        }
    });

    // Log message
    socket.on('log_message', (data) => {
        addLogMessage(data.message);
    });

    // Time update
    socket.on('time_update', (data) => {
        setElementText('current-time', data.time);
        setElementText('current-date', data.date);
    });
}

// Update keg display with new data
function updateKegDisplay(kegId, data) {
    const id = kegId;

    // Update beer remaining (text only)
    if (data.BeerRemainingOz !== undefined) {
        setElementText(`remaining-${id}`, data.BeerRemainingOz.toFixed(1));
    }

    // Update pour amount (text only)
    if (data.PourAmtOz !== undefined) {
        setElementText(`pour-amt-${id}`, data.PourAmtOz.toFixed(1));

        // Show popup if pour just finished (amount > 0 and status changing to Ready)
        if (data.PourAmtOz > 0.1 && data.PourStatus === 'Ready') {
            showPourPopup(kegId, data);
        }
    }

    // Update pour cost
    if (data.PourCost !== undefined) {
        setElementText(`pour-cost-${id}`, data.PourCost.toFixed(2));
    }

    // Update flow rate
    if (data.InstFlowRateOzS !== undefined) {
        setElementText(`flow-rate-${id}`, data.InstFlowRateOzS.toFixed(1));
    }

    // Update keg fill percent
    if (data.KegFillPercent !== undefined) {
        updateProgressBar(id, data.KegFillPercent);
    }

    // Update pour status
    if (data.PourStatus) {
        setPourStatus(id, data.PourStatus);
    }
}

// Animate number changes
function animateNumber(elementId, newValue, decimals = 0) {
    const element = document.getElementById(elementId);
    if (!element) return;

    const oldValue = parseFloat(element.textContent) || 0;

    // Skip if value hasn't changed significantly
    if (Math.abs(newValue - oldValue) < 0.01) return;

    // Just update the value directly, no animation steps
    element.classList.add('animating');
    setTimeout(() => element.classList.remove('animating'), 300);
    element.textContent = newValue.toFixed(decimals);
}

// Update progress bar
function updateProgressBar(kegId, percent) {
    const progressFill = document.getElementById(`progress-${kegId}`);
    const percentText = document.getElementById(`percent-text-${kegId}`);

    if (progressFill) {
        progressFill.style.width = `${Math.max(0, Math.min(100, percent))}%`;
    }

    if (percentText) {
        const roundedPercent = Math.round(percent);
        percentText.textContent = roundedPercent === 0 ? 'n/a' : `${roundedPercent}%`;
    }
}

// Set pour status
function setPourStatus(kegId, status) {
    const statusElement = document.getElementById(`status-${kegId}`);
    const kegCard = document.querySelector(`#keg-${kegId} .keg-card`);

    if (!statusElement || !kegCard) return;

    const statusText = statusElement.querySelector('.status-text');
    const statusDot = statusElement.querySelector('.status-dot');

    // Update text
    if (statusText) {
        statusText.textContent = status;
    }

    // Update visual state
    statusElement.classList.remove('pouring', 'empty');
    kegCard.classList.remove('pouring');

    if (status === 'Pour Active') {
        statusElement.classList.add('pouring');
        kegCard.classList.add('pouring');
    } else if (status === 'Keg Empty') {
        statusElement.classList.add('empty');
    }
}

// Show pour completion popup
function showPourPopup(kegId, pourData) {
    // Clear any existing popup timeout
    if (pourPopupTimeout) {
        clearTimeout(pourPopupTimeout);
    }

    // Get keg config
    const kegConfig = config.kegs[kegId] || {};

    // Create popup if it doesn't exist
    let popup = document.getElementById('pour-popup');
    if (!popup) {
        popup = createPourPopup();
        document.body.appendChild(popup);
    }

    // Get Venmo logo
    const venmoLogo = document.querySelector('.venmo-logo');

    // Move Venmo logo to popup
    const popupLogo = popup.querySelector('.popup-venmo-logo');
    if (venmoLogo && popupLogo) {
        const logoClone = venmoLogo.cloneNode(true);
        popupLogo.innerHTML = '';
        popupLogo.appendChild(logoClone);
        venmoLogo.style.opacity = '0';
    }

    // Populate popup data
    popup.querySelector('.popup-beer-name').textContent = kegConfig.name || 'Beer';
    popup.querySelector('.popup-brewery-name').textContent = kegConfig.brewery || '';
    popup.querySelector('.popup-pour-amount').textContent = pourData.PourAmtOz.toFixed(1);
    popup.querySelector('.popup-pour-cost').textContent = pourData.PourCost.toFixed(2);
    popup.querySelector('.popup-flow-rate').textContent = pourData.InstFlowRateOzS.toFixed(1);

    // Show popup
    popup.classList.add('visible');

    // Hide popup after 10 seconds
    pourPopupTimeout = setTimeout(() => {
        hidePourPopup();
    }, 10000);
}

// Hide pour popup
function hidePourPopup() {
    const popup = document.getElementById('pour-popup');
    const venmoLogo = document.querySelector('.venmo-logo');

    if (popup) {
        popup.classList.remove('visible');

        // Return Venmo logo to header after animation
        setTimeout(() => {
            if (venmoLogo) {
                venmoLogo.style.opacity = '1';
            }
        }, 500);
    }
}

// Create pour popup element
function createPourPopup() {
    const popup = document.createElement('div');
    popup.id = 'pour-popup';
    popup.className = 'pour-popup';
    popup.innerHTML = `
        <div class="popup-content">
            <div class="popup-header">
                <h2>Pour Complete! 🍺</h2>
                <button class="popup-close" onclick="hidePourPopup()">×</button>
            </div>
            <div class="popup-body">
                <div class="popup-venmo-logo"></div>
                <div class="popup-beer-info">
                    <div class="popup-beer-name">Beer Name</div>
                    <div class="popup-brewery-name">Brewery</div>
                </div>
                <div class="popup-stats">
                    <div class="popup-stat">
                        <div class="popup-stat-label">Amount Poured</div>
                        <div class="popup-stat-value"><span class="popup-pour-amount">0.0</span> fl oz</div>
                    </div>
                    <div class="popup-stat">
                        <div class="popup-stat-label">Cost</div>
                        <div class="popup-stat-value">$<span class="popup-pour-cost">0.00</span></div>
                    </div>
                    <div class="popup-stat">
                        <div class="popup-stat-label">Flow Rate</div>
                        <div class="popup-stat-value"><span class="popup-flow-rate">0.0</span> oz/s</div>
                    </div>
                </div>
                <div class="popup-footer">
                    Scan QR code to pay with Venmo
                </div>
            </div>
        </div>
    `;
    return popup;
}

// Add log message
function addLogMessage(message) {
    const logContent = document.getElementById('log-messages');
    if (!logContent) return;

    const messageDiv = document.createElement('div');
    messageDiv.className = 'log-message';
    messageDiv.textContent = message;

    logContent.appendChild(messageDiv);

    // Auto-scroll to bottom
    logContent.scrollTop = logContent.scrollHeight;

    // Limit log messages to last 100
    const messages = logContent.querySelectorAll('.log-message');
    if (messages.length > 100) {
        messages[0].remove();
    }
}

// Update time/date
function updateTime() {
    const now = new Date();
    const time = now.toLocaleTimeString('en-US', { hour12: false });
    const month = now.getMonth() + 1;
    const day = now.getDate();
    const year = now.getFullYear();
    const date = `${month}/${day}/${year}`;

    setElementText('current-time', time);
    setElementText('current-date', date);
}

// Utility: Set element text safely
function setElementText(elementId, text) {
    const element = document.getElementById(elementId);
    if (element) {
        element.textContent = text;
    }
}
