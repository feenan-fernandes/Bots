// DOM Elements
const navDashboard = document.getElementById('nav-dashboard');
const navSettings = document.getElementById('nav-settings');
const navML = document.getElementById('nav-ml');
const navLogout = document.getElementById('nav-logout');
const viewDashboard = document.getElementById('view-dashboard');
const viewSettings = document.getElementById('view-settings');

const sysPulse = document.getElementById('system-pulse');
const sysStatusText = document.getElementById('system-status-text');
const btnRun = document.getElementById('btn-run');
const btnRefresh = document.getElementById('btn-refresh');
const btnEmergency = document.getElementById('btn-emergency');
const btnResume = document.getElementById('btn-resume');

const toastEl = document.getElementById('toast');

// Login Elements
const loginOverlay = document.getElementById('login-overlay');
const loginForm = document.getElementById('login-form');
const loginPassphrase = document.getElementById('login_passphrase');
const btnLogin = document.getElementById('btn-login');

// Global Auth State
let csrfToken = '';

// Security: Initialize CSRF Token
async function initCSRF() {
    try {
        const res = await fetch('/api/csrf', { cache: 'no-store', credentials: 'same-origin' });
        if (res.ok) {
            const data = await res.json();
            csrfToken = data.csrf_token;
        }
    } catch (e) {
        console.error("Failed to load CSRF token.");
    }
}

// Security: Secure Fetch Wrapper
async function secureFetch(url, options = {}) {
    if (!csrfToken) await initCSRF();
    if (!options.headers) options.headers = {};
    if (options.method && options.method !== 'GET') {
        options.headers['X-CSRFToken'] = csrfToken;
    }
    options.credentials = 'same-origin';
    
    const res = await fetch(url, options);
    
    if (res.status === 401) {
        // Unauthorized, show login overlay
        loginOverlay.classList.add('active');
        throw new Error("Unauthorized");
    }
    return res;
}

// Login Logic
loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const passphrase = loginPassphrase.value;
    
    const btnText = btnLogin.querySelector('.btn-text');
    const loader = document.getElementById('login-loader');
    btnText.style.display = 'none';
    loader.style.display = 'block';

    try {
        await initCSRF(); // Ensure fresh token before auth
        const res = await fetch('/api/login', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ passphrase })
        });
        
        if (res.ok) {
            loginOverlay.classList.remove('active');
            loginPassphrase.value = '';
            showToast('Authenticated successfully.');
            // Reload dashboard data
            fetchStatus();
            fetchChartData();
        } else {
            showToast('Invalid passphrase.');
        }
    } catch (err) {
        showToast('Login error.');
    } finally {
        btnText.style.display = 'block';
        loader.style.display = 'none';
    }
});

// Logout Logic
navLogout.addEventListener('click', async () => {
    try {
        await secureFetch('/api/logout', { method: 'POST' });
        loginOverlay.classList.add('active');
        showToast('Logged out.');
    } catch (e) {
        console.error("Logout failed", e);
    }
});

// Navigation Logic
navDashboard.addEventListener('click', () => {
    navDashboard.classList.add('active');
    navSettings.classList.remove('active');
    if (navML) navML.classList.remove('active');
    viewDashboard.classList.add('active');
    viewSettings.classList.remove('active');
    if (viewAnalytics) viewAnalytics.classList.remove('active');
    fetchStatus();
    fetchChartData();
});

navSettings.addEventListener('click', () => {
    navSettings.classList.add('active');
    navDashboard.classList.remove('active');
    if (navML) navML.classList.remove('active');
    viewSettings.classList.add('active');
    viewDashboard.classList.remove('active');
    if (viewAnalytics) viewAnalytics.classList.remove('active');
    checkConfigStatus();
});

const viewAnalytics = document.getElementById('view-analytics');

if (navML) {
    navML.addEventListener('click', () => {
        navML.classList.add('active');
        navDashboard.classList.remove('active');
        navSettings.classList.remove('active');
        if (viewAnalytics) viewAnalytics.classList.add('active');
        viewDashboard.classList.remove('active');
        viewSettings.classList.remove('active');
        fetchAnalytics(); // Fetch data when opening tab
    });
}

// Toast Utility
function showToast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.add('show');
    setTimeout(() => toastEl.classList.remove('show'), 3000);
}

// Formatters
const fmtCurrency = (val) => new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(val);
const fmtCrypto = (val) => new Intl.NumberFormat('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 6 }).format(val);
const fmtPct = (val) => (val > 0 ? '+' : '') + new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(val) + '%';

// Smooth counting animation for numerical updates
function animateValue(elementId, start, end, duration, formatter) {
    const el = document.getElementById(elementId);
    if (!el) return;
    
    // Check if the current value is already equal to avoid re-triggering
    if (el.dataset.val === String(end)) return;
    el.dataset.val = String(end);

    let startTimestamp = null;
    const step = (timestamp) => {
        if (!startTimestamp) startTimestamp = timestamp;
        const progress = Math.min((timestamp - startTimestamp) / duration, 1);
        // easeOutQuart
        const ease = 1 - Math.pow(1 - progress, 4);
        const current = start + (end - start) * ease;
        
        el.innerHTML = formatter ? formatter(current) : current.toFixed(2);
        
        if (progress < 1) {
            window.requestAnimationFrame(step);
        } else {
            el.innerHTML = formatter ? formatter(end) : end.toFixed(2);
        }
    };
    window.requestAnimationFrame(step);
}

// --- Chart Logic ---
let chart;
let activeChartSymbol = 'BTCUSDT';
let userSelectedChartSymbol = false;
let activeChartInterval = '1h';

function initChart() {
    const container = document.querySelector('#chart-container');
    if (!container) return;

    const options = {
        series: [],
        chart: {
            type: 'candlestick',
            height: 360,
            background: 'transparent',
            toolbar: { show: false },
            animations: { enabled: true, dynamicAnimation: { speed: 400 } },
            dropShadow: {
                enabled: true,
                top: 2,
                left: 0,
                blur: 8,
                color: '#39ff14',
                opacity: 0.2
            }
        },
        theme: { mode: 'dark' },
        plotOptions: {
            candlestick: {
                colors: { upward: '#39ff14', downward: '#ff3366' },
                wick: { useFillColor: true }
            }
        },
        xaxis: {
            type: 'datetime',
            labels: { style: { colors: '#8b949e', fontFamily: 'Inter' } },
            axisBorder: { show: false },
            axisTicks: { show: false }
        },
        yaxis: {
            tooltip: { enabled: true },
            labels: { 
                style: { colors: '#8b949e', fontFamily: 'Inter' },
                formatter: (value) => { return value.toFixed(4); }
            },
            min: (min) => { return min * 0.995; },
            max: (max) => { return max * 1.005; }
        },
        grid: {
            borderColor: 'rgba(255,255,255,0.03)',
            strokeDashArray: 0,
            xaxis: { lines: { show: true } },
            yaxis: { lines: { show: true } }
        },
        stroke: {
            curve: 'smooth',
            width: [1, 2, 2], // 1 for candles, 2 for Kalman, 2 for VWAP
            colors: ['transparent', '#ffb300', '#00e676']
        }
    };
    
    chart = new ApexCharts(container, options);
    chart.render();
}

async function fetchChartData() {
    if (!chart) return;
    try {
        const res = await secureFetch(`/api/chart?symbol=${activeChartSymbol}&interval=${activeChartInterval}`);
        const json = await res.json();
        
        // Update Chart Title
        const displaySym = activeChartSymbol.replace('USDT', '');
        const chartTitle = document.getElementById('chart-title');
        if (chartTitle) chartTitle.textContent = `Live Market View (${displaySym})`;
        
        if (json.status === 'success' && json.data) {
            const candles = json.data.map(d => ({
                x: d.time * 1000,
                y: [d.open, d.high, d.low, d.close]
            }));
            
            const kalman = json.data.filter(d => d.kalman !== null && d.kalman !== undefined).map(d => ({
                x: d.time * 1000,
                y: d.kalman
            }));
            
            const vwap = json.data.filter(d => d.vwap !== null && d.vwap !== undefined).map(d => ({
                x: d.time * 1000,
                y: d.vwap
            }));
            
            chart.updateSeries([{
                name: 'Candles',
                type: 'candlestick',
                data: candles
            }, {
                name: 'Kalman Filter',
                type: 'line',
                data: kalman,
                color: '#ffaa00'
            }, {
                name: 'VWAP',
                type: 'line',
                data: vwap,
                color: '#3498db'
            }]);
        }
    } catch (e) {
        if (e.message !== "Unauthorized") console.error("Failed to load chart data", e);
    }
}

// Fetch Bot Status
async function fetchStatus() {
    try {
        const [statusRes, healthRes] = await Promise.all([
            secureFetch('/status'),
            secureFetch('/health') // Route through secureFetch to handle 401s
        ]);
        
        if (!statusRes.ok || !healthRes.ok) {
            // Stay connected if there's a 500 API error
            return;
        }

        const status = await statusRes.json();
        const health = await healthRes.json();
        
        updateDashboard(status, health);
    } catch (e) {
        if (e.message === "Unauthorized") {
            // Already handled in secureFetch (overlay is shown)
            return;
        }
        console.error("Dashboard update failed:", e);
        sysPulse.classList.add('halted');
        sysStatusText.textContent = 'Disconnected';
    }
}

function updateDashboard(status, health) {
    document.getElementById('login-overlay').classList.remove('active');
    window.nextScanTime = status.next_scan_time || 0;
    
    // Update active chart symbol dynamically
    if (!userSelectedChartSymbol) {
        let newChartSymbol = activeChartSymbol;
        if (status.open_trades && status.open_trades.length > 0) {
            newChartSymbol = status.open_trades[0].symbol;
        } else if (status.top_candidates && status.top_candidates.length > 0) {
            newChartSymbol = status.top_candidates[0].symbol;
        }
        if (newChartSymbol !== activeChartSymbol) {
            activeChartSymbol = newChartSymbol;
            fetchChartData();
        }
    }
    // Top Bar Status
    const pmToggle = document.getElementById('paper_mode_toggle');
    if (pmToggle && document.activeElement !== pmToggle) {
        pmToggle.checked = health.paper_mode;
    }

    if (status.halted) {
        sysPulse.classList.add('halted');
        sysPulse.classList.remove('active');
        sysStatusText.textContent = 'Bot Halted';
        btnEmergency.style.display = 'none';
        btnResume.style.display = 'inline-flex';
    } else {
        sysPulse.classList.remove('halted');
        sysPulse.classList.add('active');
        sysStatusText.textContent = health.paper_mode ? 'Autotrading Active (Paper)' : 'Autotrading Active (Live)';
        btnEmergency.style.display = 'inline-flex';
        btnResume.style.display = 'none';
    }

    // Metrics
    document.getElementById('val-portfolio-aed').textContent = fmtCurrency(health.portfolio_aed);
    const portUsd = health.portfolio_aed / 3.6725;
    document.getElementById('val-portfolio-usd').textContent = fmtCurrency(portUsd);
    
    // Utilization
    const utilUsd = (status.open_trades || []).reduce((acc, t) => acc + (t.price * t.qty), 0);
    const utilBadge = document.getElementById('val-utilized-usd');
    if (utilBadge) {
        utilBadge.textContent = `$${fmtCurrency(utilUsd)}`;
        const utilizedPct = portUsd > 0 ? Math.min(100, (utilUsd / portUsd) * 100) : 0;
        document.getElementById('val-utilized-bar').style.width = utilizedPct + '%';
        document.getElementById('val-utilized-bar').style.background = utilizedPct > 75 ? 'var(--danger)' : (utilizedPct > 40 ? 'var(--warning)' : 'var(--primary)');
    }

    const portAed = health.portfolio_aed || 0;
    const oldPortAed = parseFloat(document.getElementById('val-portfolio-aed').dataset.val) || 0;
    const oldPortUsd = parseFloat(document.getElementById('val-portfolio-usd').dataset.val) || 0;
    animateValue('val-portfolio-aed', oldPortAed, portAed, 800, fmtCurrency);
    animateValue('val-portfolio-usd', oldPortUsd, portUsd, 800, fmtCurrency);
    
    const pnlAed = status.daily_stats.pnl_aed || 0;
    const pnlUsd = status.daily_stats.pnl_usd || 0;
    const pnlEl = document.getElementById('val-daily-pnl');
    
    // Only update innerHTML if it's not currently animating or if we skip animation for this
    const oldPnlAed = parseFloat(pnlEl.dataset.val) || 0;
    if (oldPnlAed !== pnlAed) {
        animateValue('val-daily-pnl', oldPnlAed, pnlAed, 800, (v) => `<span class="currency">AED</span> ${fmtCurrency(v)}`);
        pnlEl.className = 'value ' + (pnlAed >= 0 ? 'pos' : 'neg');
    }
    
    const oldPnlUsd = parseFloat(document.getElementById('val-daily-pnl-usd').dataset.val) || 0;
    animateValue('val-daily-pnl-usd', oldPnlUsd, pnlUsd, 800, fmtCurrency);

    const trades = status.daily_stats.trades || 0;
    const wins = status.daily_stats.wins || 0;
    document.getElementById('val-win-rate').textContent = trades > 0 ? Math.round((wins / trades) * 100) + '%' : '0%';
    document.getElementById('val-trades-count').textContent = `${trades} Trades Today`;

    // Active Trades
    const atContainer = document.getElementById('active-trade-container');
    const atSplit = document.getElementById('active-trades-split');
    
    if (status.open_trades && status.open_trades.length > 0) {
        if (atSplit) {
            const longs = status.open_trades.filter(t => t.side === 'LONG').length;
            const shorts = status.open_trades.filter(t => t.side === 'SHORT').length;
            let splitHtml = '';
            if (longs > 0) splitHtml += `<span style="color: var(--success); background: rgba(16, 185, 129, 0.1); padding: 2px 6px; border-radius: 4px; border: 1px solid rgba(16, 185, 129, 0.3);">${longs} LONG</span>`;
            if (shorts > 0) splitHtml += `<span style="color: var(--danger); background: rgba(239, 68, 68, 0.1); padding: 2px 6px; border-radius: 4px; border: 1px solid rgba(239, 68, 68, 0.3);">${shorts} SHORT</span>`;
            atSplit.innerHTML = splitHtml;
        }

        atContainer.innerHTML = status.open_trades.map(t => {
            const side = t.side || "LONG";
            const sideColor = side === "LONG" ? "var(--success)" : "var(--danger)";
            
            return `
            <div class="trade-row" style="display: flex; justify-content: space-between; align-items: center; padding: 0.6rem 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.05); background: rgba(0,0,0,0.1); transition: background 0.2s;">
                <div style="width: 90px; flex-shrink: 0;">
                    <div style="font-weight: 700; color: #fff; font-size: 0.85rem;">${t.symbol}</div>
                    <div style="color: ${sideColor}; font-size: 0.65rem; font-weight: 800; margin-top: 2px;">${side}</div>
                </div>
                
                <div style="flex: 1; min-width: 0; font-size: 0.7rem; color: var(--text-muted); line-height: 1.4;">
                    <div>Entry: <span style="color: #fff; font-weight: 500;">$${fmtCrypto(t.price)}</span></div>
                    <div>Qty: <span style="color: #fff; font-weight: 500;">${fmtCrypto(t.qty)}</span></div>
                </div>
                
                <div style="flex: 1.2; min-width: 0; text-align: right; font-size: 0.7rem; line-height: 1.4;">
                    <div style="color: var(--success);">TP: $${fmtCrypto(t.take_profit)}</div>
                    <div id="current-price-badge-${t.symbol}" style="font-weight: 700; color: #fff; font-size: 0.8rem; margin: 2px 0;">Wait...</div>
                    <div style="color: var(--danger);">SL: $${fmtCrypto(t.stop_loss)}</div>
                </div>
            </div>
            `;
        }).join('');
        
        // Fetch current price for concise rows
        setTimeout(() => {
            status.open_trades.forEach(async (t) => {
                try {
                    const res = await secureFetch(`/api/chart?symbol=${t.symbol}&interval=5m`);
                    const json = await res.json();
                    if (json.status === 'success' && json.data && json.data.length > 0) {
                        const currentPrice = json.data[json.data.length - 1].close;
                        const priceBadge = document.getElementById(`current-price-badge-${t.symbol}`);
                        if (priceBadge) {
                            priceBadge.textContent = `$${fmtCrypto(currentPrice)}`;
                            priceBadge.style.color = (t.side === 'LONG' && currentPrice > t.price) || (t.side === 'SHORT' && currentPrice < t.price) 
                                ? 'var(--success)' : 'var(--danger)';
                        }
                    }
                } catch (e) { console.error('Price fetch error:', e); }
            });
        }, 100);
    } else {
        if (atSplit) atSplit.innerHTML = '';
        atContainer.innerHTML = `
            <div class="empty-state">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="1"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                <p>No active positions.</p>
            </div>
        `;
    }

    // Trade History
    const thList = document.getElementById('trade-history-list');
    if (status.recent_trades && status.recent_trades.length > 0) {
        thList.innerHTML = status.recent_trades.reverse().map(t => {
            const fmtDate = (isoStr) => {
                if (!isoStr || isoStr === "Unknown") return "Unknown";
                const d = new Date(isoStr);
                return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${d.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}`;
            };
            const entryTime = fmtDate(t.entry_time);
            const exitTime = fmtDate(t.exit_time);
            const side = t.side || "CLOSED";
            const sideColor = side === "LONG" ? "var(--success)" : (side === "SHORT" ? "var(--danger)" : "var(--text-muted)");
            const pnlColor = t.pnl_pct > 0 ? "var(--success)" : (t.pnl_pct < 0 ? "var(--danger)" : "var(--text-muted)");
            
            return `
            <li style="display: flex; justify-content: space-between; align-items: center; padding: 0.6rem 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.05); background: rgba(0,0,0,0.1); margin-bottom: 4px; border-radius: 4px; list-style: none;">
                <div style="width: 90px; flex-shrink: 0;">
                    <div style="font-weight: 700; color: #fff; font-size: 0.85rem;">${t.symbol || 'UNKNOWN'}</div>
                    <div style="color: ${sideColor}; font-size: 0.65rem; font-weight: 800; margin-top: 2px;">${side}</div>
                </div>
                
                <div style="flex: 1; min-width: 0; font-size: 0.7rem; color: var(--text-muted); line-height: 1.4;">
                    <div>In: <span style="color: #fff; font-weight: 500;">${entryTime}</span></div>
                    <div>Out: <span style="color: #fff; font-weight: 500;">${exitTime}</span></div>
                </div>
                
                <div style="flex: 1.2; min-width: 0; text-align: right; font-size: 0.7rem; line-height: 1.4;">
                    <div style="color: ${pnlColor}; font-weight: 700; font-size: 0.85rem;">${t.pnl_pct > 0 ? '+' : ''}${fmtPct(t.pnl_pct)}</div>
                    <div style="color: var(--text-muted); margin-top: 2px;">AED ${t.pnl_aed > 0 ? '+' : ''}${fmtCurrency(t.pnl_aed)}</div>
                </div>
            </li>
            `;
        }).join('');
    } else {
        thList.innerHTML = `<li class="empty-state" style="padding:1rem 0;font-size:0.9rem">No recent trades.</li>`;
    }
    
    // Strategy Brain & Chart Title
    if (status.last_analysis) {
        const a = status.last_analysis;
        
        const regEl = document.getElementById('brain-regime');
        regEl.textContent = a.regime || 'WAITING';
        if (a.regime === 'BLACK_SWAN') regEl.style.color = 'var(--danger)';
        else regEl.style.color = '';
        
        document.getElementById('brain-mtf').textContent = a.mtf || 'WAITING';
        document.getElementById('brain-score').textContent = (a.score || 0).toString();
        
        let reasonMap = {
            "no_mtf_confluence": "Timeframes disagree (1H/15m/5m mixed)",
            "black_swan": "Extreme volatility detected",
            "below_confluence_threshold": "Not enough indicators agree",
            "mtf_direction_conflict": "Timeframes conflict with signal",
            "no_signals": "Market is neutral (0 points)",
            "duplicate": "Trade already taken recently",
            "insufficient_data": "Waiting for more candle data"
        };
        
        let sigText = a.signal || 'WAITING';
        if (a.action && a.action.startsWith('SKIP')) {
            let mappedReason = a.reason ? (reasonMap[a.reason] || a.reason) : "Neutral Market";
            sigText += `<br><span style="font-size: 0.7rem; color: var(--text-muted);">(SKIPPED: ${mappedReason})</span>`;
        }
        const signalEl = document.getElementById('brain-signal');
        if (signalEl) {
            signalEl.innerHTML = sigText;
        }
        
        const blacklistEl = document.getElementById('brain-blacklist');
        if (blacklistEl) {
            let blText = status.blacklist_symbols || 'None';
            if (blText !== 'None') {
                blText = blText.split(',').map(s => s.trim().replace('USDT', '')).join(', ');
            }
            blacklistEl.textContent = blText;
            blacklistEl.title = blText;
            blacklistEl.style.flex = '1';
            blacklistEl.style.minWidth = '0';
            blacklistEl.style.marginLeft = '1rem';
            blacklistEl.style.textAlign = 'right';
            blacklistEl.style.wordBreak = 'break-word';
            blacklistEl.style.lineHeight = '1.4';
        }

        const scanEl = document.getElementById('brain-scanning');
        if (scanEl && status.scanned_symbols) {
            const scanText = status.scanned_symbols.map(s => s.replace('USDT', '')).join(', ');
            scanEl.textContent = scanText || 'None';
            scanEl.title = scanText || 'None';
            scanEl.style.flex = '1';
            scanEl.style.minWidth = '0';
            scanEl.style.marginLeft = '1rem';
            scanEl.style.textAlign = 'right';
            scanEl.style.wordBreak = 'break-word';
            scanEl.style.lineHeight = '1.4';
        }

        const breakdownContainer = document.getElementById('brain-breakdown');
        if (breakdownContainer && a.breakdown) {
            breakdownContainer.innerHTML = '';
            const keys = Object.keys(a.breakdown);
            if (keys.length === 0) {
                breakdownContainer.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 1rem 0;">No active indicators</div>';
            } else {
                const badgeContainer = document.createElement('div');
                badgeContainer.style.display = 'flex';
                badgeContainer.style.flexWrap = 'wrap';
                badgeContainer.style.gap = '0.5rem';
                
                keys.forEach(k => {
                    const pts = a.breakdown[k];
                    const badge = document.createElement('span');
                    badge.style.background = 'rgba(255,255,255,0.05)';
                    badge.style.border = '1px solid rgba(255,255,255,0.1)';
                    badge.style.padding = '2px 6px';
                    badge.style.borderRadius = '4px';
                    badge.style.fontSize = '0.7rem';
                    const labelName = k.replace(/_/g, ' ').toUpperCase();
                    badge.innerHTML = `<span style="color:var(--text-muted)">${labelName}</span> <span style="color:var(--primary);font-weight:600;">+${pts}</span>`;
                    badgeContainer.appendChild(badge);
                });
                breakdownContainer.appendChild(badgeContainer);
            }
        }

        if (a.ts) {
            const diff = Math.floor((new Date() - new Date(a.ts)) / 1000);
            let timeStr = diff < 60 ? `${diff}s ago` : `${Math.floor(diff/60)}m ago`;
            document.getElementById('brain-scan').textContent = timeStr;
        }
        
        // Render Top Candidates Table
        const tbody = document.getElementById('top-candidates-body');
        if (tbody && status.top_candidates) {
            
            const selectEl = document.getElementById('chart-symbol-select');
            if (selectEl) {
                const currentVal = selectEl.value;
                const newSymbols = status.scanned_symbols && status.scanned_symbols.length > 0 ? status.scanned_symbols : status.top_candidates.map(c => c.symbol);
                if (newSymbols.length > 0) {
                    selectEl.style.display = 'block';
                    let changed = false;
                    
                    // Only update options if list changed to avoid focus loss
                    if (selectEl.options.length !== newSymbols.length) {
                        changed = true;
                    } else {
                        for (let i=0; i<newSymbols.length; i++) {
                            if (selectEl.options[i].value !== newSymbols[i]) { changed = true; break; }
                        }
                    }
                    
                    if (changed) {
                        selectEl.innerHTML = '';
                        newSymbols.forEach(sym => {
                            const opt = document.createElement('option');
                            opt.value = sym;
                            opt.textContent = sym.replace('USDT', '');
                            selectEl.appendChild(opt);
                        });
                        
                        if (currentVal && newSymbols.includes(currentVal)) {
                            selectEl.value = currentVal;
                        } else if (!currentVal || !newSymbols.includes(activeChartSymbol)) {
                            activeChartSymbol = newSymbols[0];
                            selectEl.value = newSymbols[0];
                            fetchChartData();
                        }
                    }
                }
            }

            const getScoreBadge = (score) => {
                if (score >= 55) return `<span class="badge badge-success">${score}</span>`;
                if (score >= 35) return `<span class="badge badge-warning">${score}</span>`;
                if (score >= 20) return `<span class="badge badge-neutral">${score}</span>`;
                return `<span class="badge badge-danger">${score}</span>`;
            };
            const getIndStr = (val) => val > 0 ? `<span class="pos">+${val}</span>` : (val < 0 ? `<span class="neg">${val}</span>` : `<span style="color:var(--text-muted)">+0</span>`);
            
            const dashHTML = status.top_candidates.length === 0 
                ? '<tr><td colspan="5" style="text-align: center; padding: 2rem 0; color: var(--text-muted);">No candidates evaluated</td></tr>'
                : status.top_candidates.map(c => `
                      <tr>
                          <td style="font-weight:600;">${c.symbol.replace('USDT', '')}</td>
                          <td>${getScoreBadge(c.score)}</td>
                          <td>${getIndStr(c.breakdown?.dynamic_level_bounce || 0)}</td>
                          <td>${getIndStr(c.breakdown?.pattern || 0)}</td>
                          <td><span style="color:var(--text-muted); font-size:0.7rem;">${c.regime || '-'}</span></td>
                      </tr>
                `).join('');

            const analyticsHTML = status.top_candidates.length === 0 
                ? '<tr><td colspan="9" style="text-align: center; padding: 2rem 0; color: var(--text-muted);">No candidates evaluated</td></tr>'
                : status.top_candidates.map(c => `
                      <tr>
                          <td style="font-weight:600;">${c.symbol.replace('USDT', '')}</td>
                          <td><span style="color:var(--text-muted); font-size:0.75rem;">${c.regime || '-'}</span></td>
                          <td><span style="color:${c.signal === 'BUY' ? 'var(--success)' : (c.signal === 'SELL' ? 'var(--danger)' : 'var(--text-muted)')}; font-size:0.75rem; font-weight:600;">${c.signal || 'HOLD'}</span></td>
                          <td>${getScoreBadge(c.score)}</td>
                          <td>${getIndStr(c.breakdown?.kalman || 0)}</td>
                          <td>${getIndStr(c.breakdown?.vwap_z || 0)}</td>
                          <td>${getIndStr(c.breakdown?.cvd || 0)}</td>
                          <td>${getIndStr(c.breakdown?.exhaustion || 0)}</td>
                          <td>${getIndStr(c.breakdown?.momentum || 0)}</td>
                      </tr>
                `).join('');
                
            tbody.innerHTML = dashHTML;
            
            // Also update the analytics candidates table
            const tbodyAnalytics = document.getElementById('analytics-candidates-table');
            if (tbodyAnalytics) {
                tbodyAnalytics.innerHTML = analyticsHTML;
            }
        }
    } else {
        const chartTitle = document.getElementById('chart-title');
        if (chartTitle) chartTitle.textContent = `Live Market View (Scanning...)`;
    }
}

// Config Check
async function checkConfigStatus() {
    const alertEl = document.getElementById('config-status-alert');
    const toggleEl = document.getElementById('paper_mode_toggle');
    try {
        const res = await secureFetch('/api/config');
        const data = await res.json();
        
        if (data.paper_mode !== undefined && toggleEl) {
            toggleEl.checked = data.paper_mode;
        }

        const futuresToggleEl = document.getElementById('settings-futures-toggle');
        if (data.futures_mode !== undefined && futuresToggleEl) {
            futuresToggleEl.checked = data.futures_mode;
        }
        
        const blacklistEl = document.getElementById('blacklist_symbols');
        if (data.blacklist_symbols !== undefined && blacklistEl) {
            blacklistEl.value = data.blacklist_symbols;
        }

        // Handle Active/Saved Badges
        if (data.configured_keys) {
            const displayStyle = 'inline-block';
            document.getElementById('badge-api').style.display = data.configured_keys.api ? displayStyle : 'none';
            document.getElementById('badge-secret').style.display = data.configured_keys.secret ? displayStyle : 'none';
            document.getElementById('badge-tg-token').style.display = data.configured_keys.telegram_token ? displayStyle : 'none';
            document.getElementById('badge-tg-chat').style.display = data.configured_keys.telegram_chat_id ? displayStyle : 'none';
        }

        if (data.configured) {
            alertEl.className = 'alert alert-success';
            alertEl.textContent = '✅ API keys are configured and active.';
        } else {
            alertEl.className = 'alert alert-info';
            alertEl.textContent = '⚠️ API keys missing or using placeholders. Please update them below.';
        }
    } catch (e) {
        if (e.message !== "Unauthorized") console.error(e);
    }
}

// Config Submit
document.getElementById('config-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const key = document.getElementById('binance_api_key').value;
    const sec = document.getElementById('binance_secret').value;
    const tg = document.getElementById('telegram_token').value;
    const tgc = document.getElementById('telegram_chat_id').value;
    const blacklist = document.getElementById('blacklist_symbols').value;
    const pm = document.getElementById('paper_mode_toggle');
    const fm = document.getElementById('settings-futures-toggle');
    
    const payload = {};
    if (key) payload.binance_api_key = key;
    if (sec) payload.binance_secret = sec;
    if (tg) payload.telegram_token = tg;
    if (tgc) payload.telegram_chat_id = tgc;
    if (blacklist !== undefined) payload.blacklist_symbols = blacklist;
    if (pm) payload.paper_mode = pm.checked;
    if (fm) payload.futures_mode = fm.checked;

    if (Object.keys(payload).length === 0) {
        showToast('No fields to update.');
        return;
    }

    const btnText = document.querySelector('#btn-save-config .btn-text');
    const loader = document.getElementById('config-loader');
    
    btnText.style.display = 'none';
    loader.style.display = 'block';

    try {
        const res = await secureFetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        
        showToast(data.message || 'Config saved successfully!');
        
        // Show saved tag next to button
        const saveTag = document.getElementById('save-success-tag');
        if (saveTag) {
            saveTag.style.display = 'inline-flex';
            setTimeout(() => { saveTag.style.display = 'none'; }, 4000);
        }

        // Clear fields
        document.getElementById('binance_api_key').value = '';
        document.getElementById('binance_secret').value = '';
        document.getElementById('telegram_token').value = '';
        
        checkConfigStatus();
    } catch (err) {
        if (err.message !== "Unauthorized") showToast('Failed to save config.');
    } finally {
        btnText.style.display = 'block';
        loader.style.display = 'none';
    }
});

// Action Buttons
btnRun.addEventListener('click', async () => {
    const originalText = btnRun.textContent;
    btnRun.textContent = 'Running...';
    btnRun.disabled = true;
    try {
        const res = await secureFetch('/api/run_cycle', { method: 'POST' });
        const data = await res.json();
        if (data.action) {
            let reasonMap = {
                "no_mtf_confluence": "Timeframes disagree (1H/15m/5m mixed)",
                "black_swan": "Extreme volatility detected",
                "below_confluence_threshold": "Not enough indicators agree",
                "mtf_direction_conflict": "Timeframes conflict with signal",
                "no_signals": "Market is neutral (0 points)",
                "duplicate": "Trade already taken recently",
                "insufficient_data": "Waiting for more candle data"
            };
            let mappedReason = data.reason ? (reasonMap[data.reason] || data.reason) : "";
            let msg = `Cycle complete: ${data.action}`;
            if (mappedReason) msg += ` (${mappedReason})`;
            showToast(msg);
        } else if (data.error) {
            showToast(`Error: ${data.error}`);
        }
        setTimeout(() => {
            fetchStatus();
            fetchChartData();
        }, 500);
    } catch (e) {
        if (e.message !== "Unauthorized") showToast('Failed to execute cycle.');
    } finally {
        btnRun.textContent = originalText;
        btnRun.disabled = false;
    }
});

btnRefresh.addEventListener('click', () => {
    btnRefresh.disabled = true;
    const orig = btnRefresh.textContent;
    btnRefresh.textContent = 'Refreshing...';
    
    Promise.all([
        secureFetch('/status').then(r => r.json()),
        secureFetch('/health').then(r => r.json())
    ]).then(([status, health]) => {
        updateDashboard(status, health);
        fetchChartData();
    }).catch(e => {
        if (e.message !== "Unauthorized") console.error(e);
    }).finally(() => {
        setTimeout(() => {
            btnRefresh.disabled = false;
            btnRefresh.textContent = orig;
            showToast('UI Refreshed.');
        }, 500);
    });
});


const paperModeToggle = document.getElementById('paper_mode_toggle');
if (paperModeToggle) {
    paperModeToggle.addEventListener('change', async (e) => {
        try {
            await secureFetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ paper_mode: e.target.checked })
            });
            showToast('Paper mode updated');
            fetchStatus();
        } catch (err) {
            showToast('Failed to update paper mode');
            e.target.checked = !e.target.checked; // Revert visually
        }
    });
}

const futuresModeToggle = document.getElementById('settings-futures-toggle');
if (futuresModeToggle) {
    futuresModeToggle.addEventListener('change', async (e) => {
        try {
            await secureFetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ futures_mode: e.target.checked })
            });
            showToast('Futures mode updated. Restarting cycle...');
            fetchStatus();
        } catch (err) {
            showToast('Failed to update futures mode');
            e.target.checked = !e.target.checked; // Revert visually
        }
    });
}

btnEmergency.addEventListener('click', async () => {
    if (!confirm('Are you sure? This will sell all BTC at market price and halt the bot.')) return;
    
    const originalText = btnEmergency.textContent;
    btnEmergency.textContent = 'Closing...';
    try {
        await secureFetch('/emergency', { method: 'POST' });
        showToast('Emergency close executed.');
        setTimeout(fetchStatus, 1000);
    } catch (e) {
        if (e.message !== "Unauthorized") showToast('Error executing emergency close.');
    } finally {
        btnEmergency.textContent = originalText;
    }
});

btnResume.addEventListener('click', async () => {
    const originalText = btnResume.textContent;
    btnResume.textContent = 'Resuming...';
    try {
        await secureFetch('/resume', { method: 'POST' });
        showToast('Trading resumed.');
        setTimeout(fetchStatus, 1000);
    } catch (e) {
        if (e.message !== "Unauthorized") showToast('Error resuming trading.');
    } finally {
        btnResume.textContent = originalText;
    }
});

// --- Analytics Dashboard ---
let analyticsChart = null;
let analyticsSeries = null;

let coinDropdownPopulated = false;

async function fetchAnalytics() {
    try {
        let url = '/api/analytics';
        
        // Grab filter values
        const timeframeEl = document.getElementById('analytics-filter-timeframe');
        const coinEl = document.getElementById('analytics-filter-coin');
        const startEl = document.getElementById('analytics-filter-start');
        const endEl = document.getElementById('analytics-filter-end');
        
        const params = new URLSearchParams();
        if (coinEl && coinEl.value !== 'ALL') {
            params.append('symbol', coinEl.value);
        }
        
        if (timeframeEl) {
            const now = new Date();
            let startDate = '';
            let endDate = '';
            
            if (timeframeEl.value === 'MTD') {
                startDate = new Date(now.getFullYear(), now.getMonth(), 1).toISOString();
            } else if (timeframeEl.value === 'YTD') {
                startDate = new Date(now.getFullYear(), 0, 1).toISOString();
            } else if (timeframeEl.value === 'CUSTOM') {
                if (startEl.value) startDate = new Date(startEl.value).toISOString();
                if (endEl.value) {
                    const e = new Date(endEl.value);
                    e.setHours(23, 59, 59);
                    endDate = e.toISOString();
                }
            }
            
            if (startDate) params.append('start_date', startDate);
            if (endDate) params.append('end_date', endDate);
        }
        
        if (params.toString()) {
            url += '?' + params.toString();
        }

        const res = await secureFetch(url);
        const json = await res.json();
        if (json.status === 'success' && json.data) {
            renderAnalytics(json.data);
            
            // Populate Coin Dropdown once on first load
            if (!coinDropdownPopulated && json.data.by_symbol) {
                const select = document.getElementById('analytics-filter-coin');
                if (select) {
                    Object.keys(json.data.by_symbol).sort().forEach(sym => {
                        const opt = document.createElement('option');
                        opt.value = sym;
                        opt.textContent = sym;
                        select.appendChild(opt);
                    });
                    coinDropdownPopulated = true;
                }
            }
        }
    } catch (e) {
        console.error('Error fetching analytics:', e);
    }
}

function bindAnalyticsFilters() {
    const timeframeEl = document.getElementById('analytics-filter-timeframe');
    const startEl = document.getElementById('analytics-filter-start');
    const endEl = document.getElementById('analytics-filter-end');
    const applyBtn = document.getElementById('analytics-apply-filters');
    
    if (timeframeEl) {
        timeframeEl.addEventListener('change', (e) => {
            if (e.target.value === 'CUSTOM') {
                startEl.style.display = 'block';
                endEl.style.display = 'block';
            } else {
                startEl.style.display = 'none';
                endEl.style.display = 'none';
            }
        });
    }
    
    if (applyBtn) {
        applyBtn.addEventListener('click', () => {
            fetchAnalytics();
        });
    }
}

function renderAnalytics(data) {
    let allTimeTrades = 0;
    let allTimeWins = 0;
    if (data.by_regime) {
        Object.values(data.by_regime).forEach(stats => {
            allTimeTrades += stats.trades;
            allTimeWins += stats.wins;
        });
    }
    const winRate = allTimeTrades > 0 ? ((allTimeWins / allTimeTrades) * 100).toFixed(1) : 0;
    
    let allTimePnl = 0;
    if (data.equity_curve && data.equity_curve.length > 0) {
        allTimePnl = data.equity_curve[data.equity_curve.length - 1].value;
    }
    const totalPnl = allTimePnl.toFixed(2);

    const el = (id) => document.getElementById(id);
    if (el('analytics-total-trades')) el('analytics-total-trades').textContent = allTimeTrades;
    if (el('analytics-win-rate')) el('analytics-win-rate').textContent = winRate + '%';
    const pnlEl = el('analytics-total-pnl');
    if (pnlEl) {
        pnlEl.textContent = '$' + totalPnl;
        pnlEl.style.color = parseFloat(totalPnl) >= 0 ? '#00ff9d' : '#ff4d4d';
    }
    // Equity Curve
    const chartContainer = el('analytics-equity-chart');
    if (!analyticsChart && chartContainer && typeof ApexCharts !== 'undefined') {
        const options = {
            series: [{ name: 'Cumulative PNL', data: [] }],
            chart: { type: 'area', height: 300, background: 'transparent', toolbar: { show: false } },
            theme: { mode: 'dark' },
            colors: ['#00ff9d'],
            fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.4, opacityTo: 0.0 } },
            dataLabels: { enabled: false },
            stroke: { curve: 'stepline', width: 2 },
            xaxis: { type: 'datetime', labels: { style: { colors: '#8892b0', fontFamily: 'Inter' } }, axisBorder: { show: false }, axisTicks: { show: false } },
            yaxis: { labels: { style: { colors: '#8892b0', fontFamily: 'Inter' }, formatter: (v) => '$' + v.toFixed(2) } },
            grid: { borderColor: 'rgba(255,255,255,0.05)' }
        };
        analyticsChart = new ApexCharts(chartContainer, options);
        analyticsChart.render();
    }
    if (analyticsChart && data.equity_curve && data.equity_curve.length > 0) {
        const chartData = data.equity_curve.map(pt => [
            new Date(pt.time).getTime(), pt.value
        ]).filter(pt => !isNaN(pt[0])).sort((a,b) => a[0] - b[0]);
        
        const unique = [];
        let last = -1;
        chartData.forEach(pt => {
            if (pt[0] > last) {
                unique.push(pt);
                last = pt[0];
            } else if (pt[0] === last && unique.length > 0) {
                unique[unique.length - 1][1] = pt[1];
            }
        });
        
        if (unique.length > 0) { 
            analyticsChart.updateSeries([{ data: unique }]);
        }
    }

    // Tables
    const renderTable = (dataObj) => {
        return Object.entries(dataObj || {}).map(([key, stats]) => {
            const wr = stats.trades > 0 ? ((stats.wins / stats.trades) * 100).toFixed(1) : 0;
            const color = wr >= 50 ? 'var(--success)' : 'var(--danger)';
            return `
                <tr>
                    <td style="font-weight:500">${key}</td>
                    <td style="color:var(--text-muted)">${stats.trades}</td>
                    <td>
                        <div style="display:flex; justify-content:space-between; margin-bottom:2px;">
                            <span style="color:${color};font-weight:600">${wr}%</span>
                        </div>
                        <div class="progress-container">
                            <div class="progress-bar" style="width:${wr}%; background-color:${color}"></div>
                        </div>
                    </td>
                </tr>`;
        }).join('') || '<tr><td colspan="3" class="empty-state" style="padding: 1.5rem 0;">No data yet</td></tr>';
    };

    const regimeTable = el('analytics-regime-table');
    if (regimeTable) regimeTable.innerHTML = renderTable(data.by_regime);
    
    const symbolTable = el('analytics-symbol-table');
    if (symbolTable) symbolTable.innerHTML = renderTable(data.by_symbol);
}

// Initial boot sequence
async function boot() {
    await initCSRF();
    initChart();
    fetchStatus();
    fetchChartData();
    bindAnalyticsFilters();
}

boot();

// Update Countdown Timer & Poll Status
let pollCounter = 0;
setInterval(() => {
    if (!document.getElementById('login-overlay').classList.contains('active')) {
        pollCounter++;
        if (pollCounter >= 30) {
            pollCounter = 0;
            fetchStatus();
        }
        
        // Update countdown
        const countdownEl = document.getElementById('brain-countdown');
        if (countdownEl && window.nextScanTime) {
            let diff = Math.max(0, Math.floor(window.nextScanTime - (Date.now() / 1000)));
            let m = Math.floor(diff / 60);
            let s = diff % 60;
            if (diff === 0) {
                if (countdownEl.textContent !== "WAITING" && countdownEl.textContent !== "SCANNING...") {
                    countdownEl.textContent = "SCANNING...";
                    setTimeout(() => { if(countdownEl.textContent === 'SCANNING...') countdownEl.textContent = 'WAITING'; }, 60000);
                    // Scanner is now fully autonomous in the Python backend.
                    // We only need to fetch the updated status.
                    setTimeout(fetchStatus, 2000);
                }
            } else {
                countdownEl.textContent = `${m}m ${s}s`;
            }
        }
    }
}, 1000);

// Interval Buttons Logic
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.interval-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            // Reset styles
            document.querySelectorAll('.interval-btn').forEach(b => {
                b.style.background = 'rgba(255,255,255,0.05)';
                b.style.border = '1px solid rgba(255,255,255,0.1)';
                b.style.color = 'var(--text-muted)';
            });
            // Set active style
            e.target.style.background = 'rgba(255,255,255,0.2)';
            e.target.style.border = '1px solid rgba(255,255,255,0.3)';
            e.target.style.color = '#fff';
            
            // Update state and fetch
            activeChartInterval = e.target.getAttribute('data-interval');
            fetchChartData();
        });
    });
    
    const selectEl = document.getElementById('chart-symbol-select');
    if (selectEl) {
        selectEl.addEventListener('change', (e) => {
            activeChartSymbol = e.target.value;
            userSelectedChartSymbol = true;
            fetchChartData();
        });
    }
});
