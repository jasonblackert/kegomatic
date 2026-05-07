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
    setupSettingsMenu();
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

        // ABV - only add % if not N/A
        const abv = kegData.abv || 'N/A';
        if (abv.toLowerCase() === 'n/a' || abv === '') {
            setElementText(`abv-${id}`, abv);
        } else {
            // Remove existing % if present, then add it
            const abvValue = String(abv).replace('%', '');
            setElementText(`abv-${id}`, `${abvValue}%`);
        }

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

        // Check if this is a pour completion message and trigger popup
        if (data.message.includes('Someone just poured') && data.keg_id) {
            console.log(`Pour completion detected for keg ${data.keg_id}: ${data.message}`);

            // Parse pour amount and cost from message
            // Format: "MM-DD-YYYY - HH:MM:SS: Someone just poured X.XX oz. of BeerName from the kegomatic! The cost was $X.XX"
            const ozMatch = data.message.match(/poured\s+([\d.]+)\s+oz\./);
            const costMatch = data.message.match(/\$\s*([\d.]+)/);
            const beerNameMatch = data.message.match(/oz\.\s+of\s+(.+?)\s+from the kegomatic/);

            if (ozMatch && costMatch) {
                const pourOz = parseFloat(ozMatch[1]);
                const pourCost = parseFloat(costMatch[1]);
                const beerName = beerNameMatch ? beerNameMatch[1] : '';

                console.log(`Parsed pour data: ${pourOz} oz, $${pourCost}, beer: ${beerName}`);

                // Get current keg data for this keg
                const kegConfig = config.kegs[data.keg_id];

                // Create pour data object for popup
                const pourData = {
                    PourAmtOz: pourOz,
                    PourCost: pourCost,
                    BeerName: beerName || (kegConfig ? kegConfig.Name : 'Unknown'),
                    Brewery: kegConfig ? kegConfig.Brewery : '',
                    Logo: kegConfig ? kegConfig.Logo : ''
                };

                console.log(`✓ Triggering pour popup for keg ${data.keg_id}`);
                showPourPopup(data.keg_id, pourData);
            } else {
                console.log(`✗ Could not parse pour amount/cost from message: ${data.message}`);
            }
        }
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
        const value = data.BeerRemainingOz === 0 ? '0' : data.BeerRemainingOz.toFixed(1);
        setElementText(`remaining-${id}`, value);
    }

    // Update pour amount (text only)
    if (data.PourAmtOz !== undefined) {
        const value = data.PourAmtOz === 0 ? '0' : data.PourAmtOz.toFixed(1);
        setElementText(`pour-amt-${id}`, value);
    }

    // Update pour cost
    if (data.PourCost !== undefined) {
        const value = data.PourCost === 0 ? '$0' : `$${data.PourCost.toFixed(2)}`;
        setElementText(`pour-cost-${id}`, value);
    }

    // Update flow rate and apply glow effect
    if (data.InstFlowRateOzS !== undefined) {
        const value = data.InstFlowRateOzS === 0 ? '0' : data.InstFlowRateOzS.toFixed(1);
        setElementText(`flow-rate-${id}`, value);

        // Add/remove glow effect on flow rate
        const flowRateElement = document.getElementById(`flow-rate-${id}`);
        if (flowRateElement) {
            if (data.InstFlowRateOzS > 0) {
                flowRateElement.classList.add('flow-active');
                // Update vertical bar height (max ~3 oz/s = 100%)
                const percent = Math.min(100, (data.InstFlowRateOzS / 3) * 100);
                flowRateElement.style.setProperty('--flow-height', `${percent}%`);

                // Close popup if a new pour starts
                const existingPopup = document.getElementById('pour-popup');
                if (existingPopup && existingPopup.classList.contains('visible')) {
                    hidePourPopup();
                }
            } else {
                flowRateElement.classList.remove('flow-active');
                flowRateElement.style.setProperty('--flow-height', '0%');
            }
        }

        // Apply column highlight and progress bar animation
        const isPouring = data.InstFlowRateOzS > 0;
        updateColumnHighlight(id, isPouring);
        updateProgressBarAnimation(id, isPouring);
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

// Update column highlight during pour
function updateColumnHighlight(kegId, isPouring) {
    // Get all cells in this keg's column
    const cells = [
        document.getElementById(`logo-${kegId}`)?.parentElement,
        document.getElementById(`name-${kegId}`),
        document.getElementById(`brewery-${kegId}`),
        document.getElementById(`type-${kegId}`),
        document.getElementById(`abv-${kegId}`),
        document.getElementById(`ibu-${kegId}`),
        document.getElementById(`progress-${kegId}`)?.closest('.progress-cell'),
        document.getElementById(`remaining-${kegId}`),
        document.getElementById(`pour-amt-${kegId}`),
        document.getElementById(`pour-cost-${kegId}`),
        document.getElementById(`flow-rate-${kegId}`),
        document.getElementById(`status-${kegId}`)
    ];

    cells.forEach(cell => {
        if (cell) {
            if (isPouring) {
                cell.classList.add('pouring');
            } else {
                cell.classList.remove('pouring');
            }
        }
    });
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
        if (roundedPercent === 0) {
            percentText.textContent = 'EMPTY';
            // Also update status to Keg Empty
            const statusElement = document.getElementById(`status-${kegId}`);
            if (statusElement) {
                statusElement.classList.add('empty');
                statusElement.classList.remove('pouring');
                const statusText = statusElement.querySelector('.status-text') || statusElement;
                if (statusText.querySelector) {
                    // Has child elements, update text node
                    const textNodes = Array.from(statusText.childNodes).filter(n => n.nodeType === 3);
                    if (textNodes.length > 0) {
                        textNodes[0].textContent = 'Keg Empty';
                    }
                } else {
                    // Direct text content
                    statusElement.innerHTML = '<span class="status-dot"></span> Keg Empty';
                }
            }
        } else {
            percentText.textContent = `${roundedPercent}%`;
        }
    }
}

// Update progress bar animation during pour
function updateProgressBarAnimation(kegId, isPouring) {
    const progressFill = document.getElementById(`progress-${kegId}`);
    if (progressFill) {
        if (isPouring) {
            progressFill.classList.add('flowing');
        } else {
            progressFill.classList.remove('flowing');
        }
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

    // Remove existing popup if it exists
    const existingPopup = document.getElementById('pour-popup');
    if (existingPopup) {
        existingPopup.remove();
    }

    // Get keg config
    const kegConfig = config.kegs[kegId] || {};

    // Create new popup
    const popup = createPourPopup();
    document.body.appendChild(popup);

    // Add click listener to close popup
    popup.addEventListener('click', () => {
        hidePourPopup();
    });

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
    popup.querySelector('.popup-pour-amount').textContent = pourData.PourAmtOz.toFixed(1);
    popup.querySelector('.popup-pour-cost').textContent = pourData.PourCost.toFixed(2);

    // Show popup after a brief delay to trigger animation
    setTimeout(() => {
        popup.classList.add('visible');
    }, 10);

    // Hide popup after 10 seconds
    pourPopupTimeout = setTimeout(() => {
        hidePourPopup();
    }, 10000);
}

// Hide pour popup
function hidePourPopup() {
    const popup = document.getElementById('pour-popup');
    const venmoLogo = document.querySelector('.venmo-logo');

    if (popup && popup.classList.contains('visible')) {
        // Remove visible class to trigger fade out
        popup.classList.remove('visible');

        // Return Venmo logo to header after fade out
        setTimeout(() => {
            if (venmoLogo) {
                venmoLogo.style.opacity = '1';
            }
        }, 300);
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
            </div>
            <div class="popup-body">
                <div class="popup-venmo-logo"></div>
                <div class="popup-stats">
                    <div class="popup-stat">
                        <div class="popup-stat-label">Amount Poured (fl. oz.)</div>
                        <div class="popup-stat-value"><span class="popup-pour-amount">0.0</span></div>
                    </div>
                    <div class="popup-stat">
                        <div class="popup-stat-label">Cost</div>
                        <div class="popup-stat-value">$<span class="popup-pour-cost">0.00</span></div>
                    </div>
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
    messageDiv.className = 'log-message highlight';
    messageDiv.textContent = message;

    logContent.appendChild(messageDiv);

    // Remove highlight after 3 seconds
    setTimeout(() => {
        messageDiv.classList.remove('highlight');
    }, 3000);

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

// Settings Menu Functions
function setupSettingsMenu() {
    const settingsBtn = document.getElementById('settings-btn');
    const settingsModal = document.getElementById('settings-modal');
    const closeSettings = document.getElementById('close-settings');
    const kegFormModal = document.getElementById('keg-form-modal');
    const closeKegForm = document.getElementById('close-keg-form');
    const cancelKegForm = document.getElementById('cancel-keg-form');
    const kegForm = document.getElementById('keg-form');

    // Hover effect for settings button
    settingsBtn.addEventListener('mouseenter', () => {
        settingsBtn.style.opacity = '1';
        settingsBtn.style.transform = 'rotate(90deg) scale(1.1)';
    });

    settingsBtn.addEventListener('mouseleave', () => {
        settingsBtn.style.opacity = '0.7';
        settingsBtn.style.transform = 'rotate(0deg) scale(1)';
    });

    // Open settings modal
    settingsBtn.addEventListener('click', () => {
        updateSettingsModal();
        settingsModal.classList.add('visible');
    });

    // Close settings modal
    closeSettings.addEventListener('click', () => {
        settingsModal.classList.remove('visible');
    });

    // Close keg form modal
    closeKegForm.addEventListener('click', () => {
        kegFormModal.classList.remove('visible');
    });

    cancelKegForm.addEventListener('click', () => {
        kegFormModal.classList.remove('visible');
    });

    // Empty confirmation modal handlers
    document.getElementById('close-empty-confirm').addEventListener('click', () => {
        document.getElementById('empty-confirm-modal').classList.remove('visible');
    });

    document.getElementById('cancel-empty-confirm').addEventListener('click', () => {
        document.getElementById('empty-confirm-modal').classList.remove('visible');
    });

    document.getElementById('confirm-empty-btn').addEventListener('click', async () => {
        await setKegAsEmpty();
    });

    // Edit/Replace/Empty button handlers
    document.querySelectorAll('.btn-edit').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const kegNum = e.target.dataset.keg;
            openKegForm(kegNum, 'edit');
        });
    });

    document.querySelectorAll('.btn-empty').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const kegNum = e.target.dataset.keg;
            await showEmptyConfirmation(kegNum);
        });
    });

    document.querySelectorAll('.btn-replace').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const kegNum = e.target.dataset.keg;
            openKegForm(kegNum, 'replace');
        });
    });

    // Form submit
    kegForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await saveKegForm();
    });

    // TV settings save button
    document.getElementById('save-tv-settings').addEventListener('click', async () => {
        await saveTVSettings();
    });

    // Export backup button
    document.getElementById('export-backup').addEventListener('click', async () => {
        await exportBackup();
    });

    // Import backup file input
    document.getElementById('import-file').addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (file) {
            await importBackup(file);
            // Reset input so same file can be selected again
            e.target.value = '';
        }
    });

    // Load logos on first open
    loadLogos();
}

function updateSettingsModal() {
    // Update beer names in settings modal
    for (let i = 1; i <= 5; i++) {
        const kegData = config.kegs[i.toString()];
        if (kegData) {
            setElementText(`settings-name-${i}`, kegData.name || 'Unknown');
        }
    }

    // Load TV settings
    loadTVSettings();
}

async function loadLogos() {
    try {
        const response = await fetch('/api/logos');
        const data = await response.json();
        const logoSelect = document.getElementById('form-logo');

        logoSelect.innerHTML = '<option value="">Select a logo...</option>';
        data.logos.forEach(logo => {
            const option = document.createElement('option');
            option.value = logo;
            option.textContent = logo;
            logoSelect.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading logos:', error);
    }
}

function openKegForm(kegNum, mode) {
    const kegData = config.kegs[kegNum.toString()];
    if (!kegData) return;

    const formTitle = document.getElementById('keg-form-title');
    formTitle.textContent = mode === 'edit' ? `Edit Keg - Tap ${kegNum}` : `Replace Keg - Tap ${kegNum}`;

    // Set hidden fields
    document.getElementById('form-keg-number').value = kegNum;
    document.getElementById('form-mode').value = mode;

    // Pre-fill form with current keg data
    document.getElementById('form-name').value = kegData.name || '';
    document.getElementById('form-brewery').value = kegData.brewery || '';
    document.getElementById('form-type').value = kegData.type || '';
    document.getElementById('form-abv').value = kegData.abv || '';
    document.getElementById('form-ibu').value = kegData.ibu || '';
    document.getElementById('form-cost').value = kegData.costofkeg || '';
    document.getElementById('form-size').value = kegData.kegsizel || '';
    document.getElementById('form-logo').value = kegData.logo || '';

    // For replace mode, set date to today. For edit mode, use existing date
    if (mode === 'replace') {
        const today = new Date();
        const month = String(today.getMonth() + 1).padStart(2, '0');
        const day = String(today.getDate()).padStart(2, '0');
        const year = today.getFullYear();
        document.getElementById('form-date').value = `${month}${day}${year}`;
    } else {
        document.getElementById('form-date').value = kegData.purchasedate || '';
    }

    // Show form modal
    document.getElementById('keg-form-modal').classList.add('visible');
}

async function saveKegForm() {
    const kegNum = document.getElementById('form-keg-number').value;
    const mode = document.getElementById('form-mode').value;

    const kegData = {
        name: document.getElementById('form-name').value,
        brewery: document.getElementById('form-brewery').value,
        type: document.getElementById('form-type').value,
        abv: document.getElementById('form-abv').value,
        ibu: document.getElementById('form-ibu').value,
        costofkeg: parseFloat(document.getElementById('form-cost').value),
        kegsizel: parseFloat(document.getElementById('form-size').value),
        purchasedate: document.getElementById('form-date').value,
        logo: document.getElementById('form-logo').value
    };

    try {
        const endpoint = mode === 'edit' ? '/api/keg/edit' : '/api/keg/replace';
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                keg_number: parseInt(kegNum),
                keg_data: kegData
            })
        });

        const result = await response.json();

        if (result.success) {
            console.log('Keg saved successfully:', result);

            // Close form modal
            document.getElementById('keg-form-modal').classList.remove('visible');

            // Reload config
            await fetchInitialConfig();

            // Update settings modal
            updateSettingsModal();

            // Show success message in log
            addLogMessage(`✓ Keg ${kegNum} ${mode === 'edit' ? 'updated' : 'replaced'}: ${kegData.name}`);
        } else {
            console.error('Error saving keg:', result.error);
            alert(`Error saving keg: ${result.error}`);
        }
    } catch (error) {
        console.error('Error saving keg:', error);
        alert(`Error saving keg: ${error.message}`);
    }
}

async function loadTVSettings() {
    try {
        const response = await fetch('/api/tv/settings');
        const data = await response.json();

        if (data.success) {
            document.getElementById('tv-serial-port').value = data.settings.serialport || '';
            document.getElementById('tv-baud-rate').value = data.settings.baudrate || '';
            document.getElementById('tv-sleep-time').value = data.settings.sleeptimesec || '';
        }
    } catch (error) {
        console.error('Error loading TV settings:', error);
    }
}

async function saveTVSettings() {
    const settings = {
        serialport: document.getElementById('tv-serial-port').value,
        baudrate: parseInt(document.getElementById('tv-baud-rate').value),
        sleeptimesec: parseInt(document.getElementById('tv-sleep-time').value)
    };

    try {
        const response = await fetch('/api/tv/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(settings)
        });

        const result = await response.json();

        if (result.success) {
            console.log('TV settings saved successfully');
            addLogMessage(`✓ TV settings updated: ${settings.serialport} (restart required)`);
            alert('TV settings saved successfully!\n\nNote: Software restart required for changes to take effect.');
        } else {
            console.error('Error saving TV settings:', result.error);
            alert(`Error saving TV settings: ${result.error}`);
        }
    } catch (error) {
        console.error('Error saving TV settings:', error);
        alert(`Error saving TV settings: ${error.message}`);
    }
}

async function exportBackup() {
    try {
        addLogMessage('⏳ Creating backup...');

        const response = await fetch('/api/backup/export', {
            method: 'POST'
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        // Get filename from Content-Disposition header or use default
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = 'kegomatic_backup.tar';
        if (contentDisposition) {
            const matches = /filename="?([^"]+)"?/.exec(contentDisposition);
            if (matches) filename = matches[1];
        }

        // Download the file
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        addLogMessage(`✓ Backup exported: ${filename}`);
        console.log('Backup exported successfully');

    } catch (error) {
        console.error('Error exporting backup:', error);
        addLogMessage(`✗ Backup export failed: ${error.message}`);
        alert(`Error exporting backup: ${error.message}`);
    }
}

async function importBackup(file) {
    if (!confirm(`Import backup from ${file.name}?\n\nThis will overwrite existing configs, logos, and database.\n\nSoftware restart will be required.`)) {
        return;
    }

    try {
        addLogMessage('⏳ Importing backup...');

        const formData = new FormData();
        formData.append('backup', file);

        const response = await fetch('/api/backup/import', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (result.success) {
            addLogMessage(`✓ Backup imported successfully (restart required)`);
            alert('Backup imported successfully!\n\nSoftware restart required for changes to take effect.');
            console.log('Backup imported:', result);
        } else {
            throw new Error(result.error || 'Unknown error');
        }

    } catch (error) {
        console.error('Error importing backup:', error);
        addLogMessage(`✗ Backup import failed: ${error.message}`);
        alert(`Error importing backup: ${error.message}`);
    }
}

async function showEmptyConfirmation(kegNum) {
    try {
        // Get the calculated empty size from the server
        const response = await fetch(`/api/keg/${kegNum}/calculate-empty`);
        const result = await response.json();

        if (result.success) {
            const currentSize = result.current_size_l;
            const pouredAmount = result.poured_l;
            const newSize = result.new_size_l;

            // Store keg number for the confirmation action
            document.getElementById('confirm-empty-btn').dataset.keg = kegNum;

            // Show confirmation message
            const message = `This will update the keg size from ${currentSize.toFixed(2)} L to ${newSize.toFixed(2)} L based on ${pouredAmount.toFixed(2)} L poured.\n\nAre you sure?`;
            document.getElementById('empty-confirm-message').textContent = message;
            document.getElementById('empty-confirm-modal').classList.add('visible');
        } else {
            alert(`Error: ${result.error}`);
        }
    } catch (error) {
        console.error('Error calculating empty size:', error);
        alert(`Error calculating empty size: ${error.message}`);
    }
}

async function setKegAsEmpty() {
    const kegNum = document.getElementById('confirm-empty-btn').dataset.keg;

    try {
        // Get the calculated size
        const calcResponse = await fetch(`/api/keg/${kegNum}/calculate-empty`);
        const calcResult = await calcResponse.json();

        if (!calcResult.success) {
            throw new Error(calcResult.error);
        }

        // Get current keg data from config
        const currentKeg = config.kegs[kegNum];
        const kegData = {
            name: currentKeg.Name,
            brewery: currentKeg.Brewery,
            type: currentKeg.Type,
            abv: currentKeg.ABV,
            ibu: currentKeg.IBU,
            costofkeg: parseFloat(currentKeg.CostOfKeg),
            kegsizel: calcResult.new_size_l,  // Use calculated size
            purchasedate: currentKeg.PurchaseDate,
            logo: currentKeg.Logo
        };

        // Update via edit endpoint
        const response = await fetch('/api/keg/edit', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                keg_number: parseInt(kegNum),
                keg_data: kegData
            })
        });

        const result = await response.json();

        if (result.success) {
            // Close confirmation modal
            document.getElementById('empty-confirm-modal').classList.remove('visible');

            // Reload config
            await fetchInitialConfig();
            updateSettingsModal();

            addLogMessage(`✓ Keg ${kegNum} set as empty (restart required)`);
            alert('Keg set as empty successfully!\n\nSoftware restart required for changes to take effect.');
        } else {
            throw new Error(result.error);
        }
    } catch (error) {
        console.error('Error setting keg as empty:', error);
        alert(`Error setting keg as empty: ${error.message}`);
    }
}
