import os

js_path = os.path.join('static', 'app.js')
with open(js_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update Active Trades to support array `status.open_trades`
old_active_trade = """    // Active Trade
    const atContainer = document.getElementById('active-trade-container');
    if (status.open_trade) {
        const t = status.open_trade;
        atContainer.innerHTML = `
            <div class="active-trade-details">
                <div class="at-row"><span class="lbl">Asset</span><span class="val">${t.symbol}</span></div>
                <div class="at-row"><span class="lbl">Quantity</span><span class="val">${fmtCrypto(t.qty)}</span></div>
                <div class="at-row"><span class="lbl">Entry Price</span><span class="val">$${fmtCurrency(t.price)}</span></div>
                <div class="at-row"><span class="lbl">Regime</span><span class="val">${t.regime}</span></div>
                <div class="at-row"><span class="lbl" style="color:var(--danger)">Stop Loss</span><span class="val">$${fmtCurrency(t.stop_loss)}</span></div>
                <div class="at-row"><span class="lbl" style="color:var(--success)">Take Profit</span><span class="val">$${fmtCurrency(t.take_profit)}</span></div>
            </div>
        `;
    } else {
        atContainer.innerHTML = `
            <div class="empty-state">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="1"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                <p>No active positions.</p>
            </div>
        `;
    }"""

new_active_trade = """    // Active Trades
    const atContainer = document.getElementById('active-trade-container');
    if (status.open_trades && status.open_trades.length > 0) {
        atContainer.innerHTML = status.open_trades.map(t => `
            <div class="active-trade-details" style="margin-bottom: 1rem; padding-bottom: 1rem; border-bottom: 1px solid rgba(255,255,255,0.05);">
                <div style="font-weight: 600; margin-bottom: 0.5rem; color: #fff;">${t.symbol}</div>
                <div class="at-row"><span class="lbl">Quantity</span><span class="val">${fmtCrypto(t.qty)}</span></div>
                <div class="at-row"><span class="lbl">Entry Price</span><span class="val">$${fmtCurrency(t.price)}</span></div>
                <div class="at-row"><span class="lbl">Regime</span><span class="val">${t.regime}</span></div>
                <div class="at-row"><span class="lbl" style="color:var(--danger)">Stop Loss</span><span class="val">$${fmtCurrency(t.stop_loss)}</span></div>
                <div class="at-row"><span class="lbl" style="color:var(--success)">Take Profit</span><span class="val">$${fmtCurrency(t.take_profit)}</span></div>
            </div>
        `).join('');
    } else {
        atContainer.innerHTML = `
            <div class="empty-state">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="1"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                <p>No active positions.</p>
            </div>
        `;
    }"""

content = content.replace(old_active_trade, new_active_trade)

# 2. Add Navigation logic for ML Tab
nav_logic_old = """const navSettings = document.getElementById('nav-settings');

const viewDashboard = document.getElementById('view-dashboard');
const viewSettings = document.getElementById('view-settings');

function switchView(view) {
    if (view === 'dashboard') {
        navDashboard.classList.add('active');
        navSettings.classList.remove('active');
        viewDashboard.classList.add('active');
        viewSettings.classList.remove('active');
    } else {
        navSettings.classList.add('active');
        navDashboard.classList.remove('active');
        viewSettings.classList.add('active');
        viewDashboard.classList.remove('active');
    }
}

navDashboard.addEventListener('click', () => switchView('dashboard'));
navSettings.addEventListener('click', () => switchView('settings'));"""

nav_logic_new = """const navSettings = document.getElementById('nav-settings');
const navML = document.getElementById('nav-ml');

const viewDashboard = document.getElementById('view-dashboard');
const viewSettings = document.getElementById('view-settings');
const viewML = document.getElementById('view-ml');

function switchView(view) {
    navDashboard.classList.remove('active');
    navSettings.classList.remove('active');
    navML.classList.remove('active');
    viewDashboard.classList.remove('active');
    viewSettings.classList.remove('active');
    viewML.classList.remove('active');
    
    if (view === 'dashboard') {
        navDashboard.classList.add('active');
        viewDashboard.classList.add('active');
    } else if (view === 'settings') {
        navSettings.classList.add('active');
        viewSettings.classList.add('active');
    } else if (view === 'ml') {
        navML.classList.add('active');
        viewML.classList.add('active');
    }
}

navDashboard.addEventListener('click', () => switchView('dashboard'));
navSettings.addEventListener('click', () => switchView('settings'));
navML.addEventListener('click', () => switchView('ml'));"""

content = content.replace(nav_logic_old, nav_logic_new)

# 3. Add ML functionality at the bottom
ml_js = """
// --- ML Optimizer Logic ---
const btnTrainML = document.getElementById('btn-train-ml');
const mlStatusText = document.getElementById('ml-status-text');
const mlProgressBar = document.getElementById('ml-progress-bar');
const mlBaselinePnl = document.getElementById('ml-baseline-pnl');
const mlBestPnl = document.getElementById('ml-best-pnl');

let mlPollInterval;

btnTrainML.addEventListener('click', async () => {
    btnTrainML.disabled = true;
    try {
        await secureFetch('/api/ml/train', { method: 'POST' });
        showToast('ML Training Started');
        mlPollInterval = setInterval(fetchMLStatus, 2000);
    } catch (e) {
        showToast('Failed to start ML Training');
        btnTrainML.disabled = false;
    }
});

async function fetchMLStatus() {
    try {
        const res = await secureFetch('/api/ml/status');
        const json = await res.json();
        
        if (json.status === 'success') {
            const d = json.data;
            mlProgressBar.style.width = d.progress + '%';
            mlBaselinePnl.textContent = d.baseline_pnl.toFixed(2) + '%';
            mlBestPnl.textContent = d.best_pnl.toFixed(2) + '%';
            
            if (d.is_training) {
                mlStatusText.textContent = `Training... ${d.progress}%`;
                btnTrainML.disabled = true;
            } else {
                mlStatusText.textContent = 'Idle (Training Complete)';
                btnTrainML.disabled = false;
                if (mlPollInterval) {
                    clearInterval(mlPollInterval);
                    mlPollInterval = null;
                }
            }
        }
    } catch (e) {
        console.error('Error fetching ML status', e);
    }
}
"""
if "ML Optimizer Logic" not in content:
    content += ml_js

with open(js_path, 'w', encoding='utf-8') as f:
    f.write(content)
