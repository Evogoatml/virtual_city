// ===================== DOM =====================
const grid = document.getElementById('city-grid');
const container = document.getElementById('window-container');
const indicator = document.getElementById('connection-indicator');

// ===================== STATE =====================
const buildingMap = {};
const openWindows = new Map();
let windowZ = 10;
let nextX = 40;
let nextY = 40;

const WELCOME_INTROS = {
  city_hall: "I'm your CEO. I run daily meetings and track the whole city.",
  crypto_trading: "I trade crypto. Send a command or type your own.",
  market_data: "I stream live prices from exchanges via WebSocket.",
  finance_treasury: "I track the ledger and aggregate totals.",
  finance_building: "Finance District. Select a department below.",
  shopify: "I track store orders, revenue, and profit.",
  product_flipping: "I manage flip inventory — source, list, sell.",
  social_affiliates: "I run affiliate campaigns across platforms.",
  content_creation: "Content pipeline: idea -> draft -> publish.",
  content_automation: "AI video generation via Kling, Pika, Runway, HeyGen.",
  content_analytics: "Viral intelligence and ROI analysis.",
  sourcing_research: "I score product opportunities.",
  research_building: "Research Quarter. Select sourcing_research.",
  media_building: "Media District. Select content departments.",
  btc_recovery: "I scan recovery artifacts for on-chain BTC. tools / inventory / hunt / ingest available.",
  signal: "I watch web pages for changes, drops, and alerts.",
  scraper: "I fetch any URL with anti-bot bypass, parse to markdown.",
  web_check: "OSINT website analyzer. Start the service, scan URLs, open the room.",
};

const COMMANDS = {
  city_hall: [
    { label: 'Hold Meeting', cmd: 'meeting', desc: 'Run daily standup' },
    { label: 'City Status', cmd: 'city status', desc: 'Overview of all buildings' },
    { label: 'Departments', cmd: 'departments', desc: 'List all agents' },
  ],
  crypto_trading: [
    { label: 'Buy BTC @ 65k', cmd: 'buy BTC @ 65000', desc: 'Open long' },
    { label: 'Sell ETH @ 3.2k', cmd: 'sell ETH @ 3200', desc: 'Open short' },
    { label: 'Close BTC', cmd: 'close BTC', desc: 'Close position' },
    { label: 'Positions', cmd: 'positions', desc: 'Open positions' },
    { label: 'PnL', cmd: 'pnl', desc: 'Profit & loss' },
  ],
  market_data: [
    { label: 'Start Binance', cmd: 'start binance', desc: 'Begin streaming' },
    { label: 'Price BTC/USDT', cmd: 'price BTC/USDT', desc: 'Current price' },
    { label: 'Spread BTC/USDT', cmd: 'spread BTC/USDT', desc: 'Bid-ask spread' },
    { label: 'Snapshot', cmd: 'snapshot', desc: 'Full market view' },
    { label: 'Stats', cmd: 'stats', desc: 'Engine stats' },
    { label: 'Stop', cmd: 'stop', desc: 'Stop all streams' },
  ],
  finance_treasury: [
    { label: 'Ledger', cmd: 'ledger', desc: 'Show all entries' },
    { label: 'Summary', cmd: 'summary', desc: 'Totals' },
    { label: 'Add +5000', cmd: 'ledger add trading +5000 capital', desc: 'Credit' },
    { label: 'Add -50', cmd: 'ledger add fees -50 api fees', desc: 'Debit' },
  ],
  shopify: [
    { label: 'Revenue', cmd: 'revenue', desc: 'Total revenue' },
    { label: 'Top Products', cmd: 'top products', desc: 'Best sellers' },
    { label: 'Add Order', cmd: 'order "t-shirt" revenue 29.99 cost 8.00 dropship', desc: 'Record sale' },
  ],
  product_flipping: [
    { label: 'Inventory', cmd: 'inventory', desc: 'All items' },
    { label: 'Margins', cmd: 'margins', desc: 'Profit margins' },
    { label: 'Source Item', cmd: 'source "item name" cost 25.00', desc: 'Add to flip' },
    { label: 'List Item', cmd: 'list "item name" target 75.00', desc: 'Set sell target' },
    { label: 'Sold', cmd: 'sold "item name" for 80.00', desc: 'Record sale' },
  ],
  social_affiliates: [
    { label: 'Stats', cmd: 'stats', desc: 'Campaign stats' },
    { label: 'Campaign TikTok', cmd: 'campaign tiktok "my offer"', desc: 'New campaign' },
    { label: 'Click', cmd: 'click "my offer"', desc: 'Record click' },
    { label: 'Convert', cmd: 'convert "my offer" revenue 100.00', desc: 'Record conversion' },
  ],
  content_creation: [
    { label: 'Queue', cmd: 'queue', desc: 'Pipeline view' },
    { label: 'New Idea', cmd: 'idea "my title" for youtube', desc: 'Add idea' },
    { label: 'Draft', cmd: 'draft "my title"', desc: 'Move to draft' },
    { label: 'Publish', cmd: 'publish "my title"', desc: 'Publish content' },
  ],
  content_automation: [
    { label: 'Queue Status', cmd: 'queue status', desc: 'Pending jobs' },
    { label: 'Budget', cmd: 'budget', desc: 'Show limits' },
    { label: 'Providers', cmd: 'providers', desc: 'Available AI video providers' },
    { label: 'Process Queue', cmd: 'process queue', desc: 'Run pending' },
    { label: 'Stats', cmd: 'stats', desc: 'Generation stats' },
  ],
  content_analytics: [
    { label: 'Analyze Strategy', cmd: 'analyze strategy', desc: 'Full analysis' },
    { label: 'Viral Insights', cmd: 'viral insights', desc: 'Trending patterns' },
    { label: 'Trending 10', cmd: 'trending videos 10', desc: 'Hot videos' },
    { label: 'ROI 7 Days', cmd: 'roi analysis 7', desc: 'Return on investment' },
    { label: 'Budget Alerts', cmd: 'budget alerts', desc: 'Overspend warnings' },
  ],
  sourcing_research: [
    { label: 'Top Leads', cmd: 'top leads', desc: 'Highest scored' },
    { label: 'New Lead', cmd: 'lead "product" category electronics score 8.5', desc: 'Add opportunity' },
    { label: 'Action Lead', cmd: 'action "product name"', desc: 'Mark actioned' },
    { label: 'Reject Lead', cmd: 'reject "product name"', desc: 'Discard' },
  ],
  btc_recovery: [
    { label: 'Tools', cmd: 'tools', desc: 'List recovery scripts kit' },
    { label: 'Inventory', cmd: 'inventory', desc: 'Files moved into building' },
    { label: 'Balance', cmd: 'balance', desc: 'Total BTC across addresses' },
    { label: 'UTXOs', cmd: 'utxos', desc: 'List unspent outputs' },
    { label: 'Keys', cmd: 'keys', desc: 'Private keys in DB' },
    { label: 'Stats', cmd: 'stats', desc: 'Address & balance summary' },
    { label: 'Bot Status', cmd: 'bot status', desc: 'btc_recovery_bot_v2 status' },
    { label: 'Hunt Folder', cmd: 'hunt /path', desc: 'Scan folder for keys', prompt: 'Folder to hunt for keys', template: 'hunt {value}' },
    { label: 'Ingest Folder', cmd: 'ingest /path', desc: 'Ingest via bot v2', prompt: 'Folder to ingest', template: 'ingest {value}' },
    { label: 'Import All', cmd: 'import all /path', desc: 'Import wallets/keys', prompt: 'Folder path', template: 'import all {value}' },
    { label: 'Start Scan', cmd: 'scan', desc: 'Start chain monitor' },
  ],
  signal: [
    { label: 'Watches', cmd: 'watches', desc: 'All monitored pages' },
    { label: 'Alerts', cmd: 'alerts', desc: 'Unread changes' },
    { label: 'Check Now', cmd: 'check now', desc: 'Force check all' },
    { label: 'Add Watch', cmd: 'add watch https://example.com', desc: 'Monitor a URL', prompt: 'URL to watch', template: 'add watch {value}' },
  ],
  scraper: [
    { label: 'Scrape URL', cmd: 'scrape https://example.com', desc: 'Fetch + parse a page', prompt: 'URL to scrape', template: 'scrape {value}' },
    { label: 'Queue', cmd: 'queue', desc: 'Pending/crawled URLs' },
    { label: 'Results', cmd: 'results 10', desc: 'Recent scrapes' },
    { label: 'Stats', cmd: 'stats', desc: 'Scraper metrics' },
  ],
  web_check: [
    { label: 'Status', cmd: 'status', desc: 'Service status' },
    { label: 'Start Service', cmd: 'start', desc: 'Boot web-check on :3000' },
    { label: 'Stop Service', cmd: 'stop', desc: 'Stop web-check' },
    { label: 'Quick Scan', cmd: 'quick https://example.com', desc: 'Fast OSINT checks', prompt: 'URL to scan', template: 'quick {value}' },
    { label: 'Full Scan', cmd: 'scan https://example.com', desc: 'Full check suite', prompt: 'URL to scan', template: 'scan {value}' },
    { label: 'History', cmd: 'history', desc: 'Past scans' },
    { label: 'Open Room', cmd: 'room', desc: 'Room portal info' },
  ],
  research_building: [
    { label: 'Building Status', cmd: 'status', desc: 'Research hub report' },
    { label: 'Departments', cmd: 'departments', desc: 'List depts' },
    { label: 'Open Sourcing', cmd: '__open:sourcing_research', desc: 'Open sourcing_research window' },
    { label: 'Open Web-Check', cmd: '__open:web_check', desc: 'Open web_check room agent' },
  ],
  media_building: [
    { label: 'Status', cmd: 'status', desc: 'Media hub' },
    { label: 'Open Content', cmd: '__open:content_creation', desc: 'Content creation' },
    { label: 'Open Automation', cmd: '__open:content_automation', desc: 'Content automation' },
    { label: 'Open Analytics', cmd: '__open:content_analytics', desc: 'Content analytics' },
  ],
  finance_building: [
    { label: 'Aggregate', cmd: 'aggregate', desc: 'Combined report' },
    { label: 'Open Trading', cmd: '__open:crypto_trading', desc: 'Crypto trading' },
    { label: 'Open BTC Recovery', cmd: '__open:btc_recovery', desc: 'BTC recovery' },
    { label: 'Open Market Data', cmd: '__open:market_data', desc: 'Market data' },
    { label: 'Open Treasury', cmd: '__open:finance_treasury', desc: 'Treasury' },
  ],
};

// ===================== BUILDING CARDS =====================
function escText(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function renderGrid() {
  grid.innerHTML = '';
  const buildings = Object.values(buildingMap).sort((a, b) => a.name.localeCompare(b.name));
  for (const b of buildings) {
    const card = document.createElement('div');
    card.className = 'building-card' + (openWindows.has(b.name) ? ' is-open' : '');
    card.dataset.name = b.name;
    card.tabIndex = 0;
    card.setAttribute('role', 'button');
    card.setAttribute('aria-label', 'Open ' + (b.subject || b.name));
    card.title = 'Click to open · ' + (b.subject || b.name) + ' (' + (b.district || '') + ')';
    const hasWin = openWindows.has(b.name);
    const depts = (b.departments && b.departments.length)
      ? '<div class="dept-line">' + b.departments.length + ' depts</div>'
      : '';
    card.innerHTML = `
      <div class="color-bar" style="background:${b.color || '#607d8b'}"></div>
      <div class="name">${escText(b.name)}</div>
      <div class="subject">${escText(b.subject || '')}</div>
      <div class="district">${escText(b.district || '')}</div>
      <div class="status-dot ${b.status || 'idle'}"></div>
      <div class="stat-line">${b.activity_count || 0} events</div>
      ${depts}
      <div class="click-hint">click to interact</div>
      <div class="window-indicator ${hasWin ? 'open' : ''}"></div>
    `;
    card.addEventListener('click', () => toggleWindow(b.name));
    card.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        toggleWindow(b.name);
      }
    });
    grid.appendChild(card);
  }
  if (!buildings.length) {
    grid.innerHTML = '<div class="empty-city">Connecting to city stream…</div>';
  }
}

function updateCard(name) {
  const b = buildingMap[name];
  if (!b) return;
  const cards = grid.querySelectorAll('.building-card');
  for (let i = 0; i < cards.length; i++) {
    if (cards[i].dataset.name === name || cards[i].querySelector('.name').textContent === name) {
      cards[i].classList.toggle('is-open', openWindows.has(name));
      cards[i].querySelector('.stat-line').textContent = (b.activity_count || 0) + ' events';
      const dot = cards[i].querySelector('.status-dot');
      if (dot) dot.className = 'status-dot ' + (b.status || 'idle');
      const ind = cards[i].querySelector('.window-indicator');
      if (ind) ind.className = 'window-indicator' + (openWindows.has(name) ? ' open' : '');
      break;
    }
  }
}

// ===================== TOGGLE WINDOW =====================
function toggleWindow(name) {
  if (openWindows.has(name)) {
    focusWindow(name);
  } else {
    openWindow(name);
  }
}

function focusWindow(name) {
  const w = openWindows.get(name);
  if (!w) return;
  w.el.style.zIndex = ++windowZ;
  if (w.el.classList.contains('minimized')) {
    w.el.classList.remove('minimized');
  }
}

// ===================== OPEN WINDOW =====================
function openWindow(name) {
  if (openWindows.has(name)) return focusWindow(name);
  const b = buildingMap[name];
  if (!b) return;

  const chatHistory = [];
  const state = { name, chatHistory, el: null, monitorInterval: null };

  // ---- BUILD DOM ----
  const win = document.createElement('div');
  win.className = 'float-window';
  win.style.left = nextX + 'px';
  win.style.top = nextY + 'px';
  win.style.zIndex = ++windowZ;
  state.el = win;

  // Cascade next window
  nextX = (nextX + 40) % (container.clientWidth - 420 || 800);
  nextY = (nextY + 40) % (container.clientHeight - 520 || 600);
  if (nextX < 20) nextX = 40;
  if (nextY < 20) nextY = 40;

  // Header
  const header = document.createElement('div');
  header.className = 'win-header';
  header.innerHTML = `
    <div class="win-title">
      <span class="win-color" style="background:${b.color || '#607d8b'}"></span>
      ${b.subject}
    </div>
    <div class="win-actions">
      <button class="win-min">_</button>
      <button class="win-close">x</button>
    </div>
  `;
  win.appendChild(header);

  // Tabs
  const tabs = document.createElement('div');
  tabs.className = 'win-tabs';
  tabs.innerHTML = `
    <button class="win-tab active" data-pane="chat">Chat</button>
    <button class="win-tab" data-pane="plan">Plan</button>
    <button class="win-tab" data-pane="monitor">Monitor</button>
  `;
  win.appendChild(tabs);

  // Body
  const body = document.createElement('div');
  body.className = 'win-body';

  // Chat pane
  const chatPane = document.createElement('div');
  chatPane.className = 'win-pane active';
  chatPane.dataset.pane = 'chat';
  chatPane.innerHTML = `
    <div class="win-chat-messages"></div>
    <div class="win-chat-input">
      <input type="text" placeholder="Type a command..." />
      <button>Send</button>
    </div>
  `;
  body.appendChild(chatPane);

  // Plan pane
  const planPane = document.createElement('div');
  planPane.className = 'win-pane';
  planPane.dataset.pane = 'plan';
  planPane.innerHTML = `
    <div class="win-plan">
      <div style="display:flex;align-items:center;gap:6px;">
        <strong style="font-size:11px;">Plan</strong>
        <span class="plan-status-badge active">active</span>
        <span class="plan-meta"></span>
      </div>
      <textarea placeholder="Write your plan for this building... e.g.:%0ABuild a crypto trading strategy that targets 5% monthly returns with strict risk management."></textarea>
      <div class="plan-actions">
        <button class="plan-save-btn">Save Plan</button>
        <button class="plan-complete-btn">Mark Complete</button>
      </div>
    </div>
  `;
  body.appendChild(planPane);

  // Monitor pane
  const monitorPane = document.createElement('div');
  monitorPane.className = 'win-pane';
  monitorPane.dataset.pane = 'monitor';
  monitorPane.innerHTML = `<div class="win-monitor"><p class="hint">Loading monitor...</p></div>`;
  body.appendChild(monitorPane);

  win.appendChild(body);
  container.appendChild(win);

  // ---- EVENTS ----

  // Tab switching
  tabs.querySelectorAll('.win-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.querySelectorAll('.win-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      body.querySelectorAll('.win-pane').forEach(p => p.classList.remove('active'));
      const pane = body.querySelector('.win-pane[data-pane="' + tab.dataset.pane + '"]');
      if (pane) pane.classList.add('active');
      if (tab.dataset.pane === 'plan') loadPlan(state);
      if (tab.dataset.pane === 'monitor') loadMonitor(state);
      if (tab.dataset.pane === 'chat') {
        const inp = body.querySelector('.win-chat-input input');
        if (inp) setTimeout(() => inp.focus(), 50);
      }
    });
  });

  // Chat: send on button click or Enter
  const chatInput = chatPane.querySelector('input');
  const sendBtn = chatPane.querySelector('button');
  const msgContainer = chatPane.querySelector('.win-chat-messages');

  function sendChatMessage(cmd) {
    if (!cmd || !cmd.trim()) return;
    chatInput.value = '';
    runAgentCommand(state, cmd.trim());
  }

  sendBtn.addEventListener('click', () => sendChatMessage(chatInput.value));
  chatInput.addEventListener('keydown', e => { if (e.key === 'Enter') sendChatMessage(chatInput.value); });

  // Show welcome + command buttons
  const intro = WELCOME_INTROS[name];
  if (intro) appendChatMsg(msgContainer, 'agent', intro, '');
  renderCommandButtons(msgContainer, state);

  // Plan: save
  const textarea = planPane.querySelector('textarea');
  planPane.querySelector('.plan-save-btn').addEventListener('click', () => {
    const text = textarea.value.trim();
    if (!text) return;
    fetch('/api/plan', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_name: name, plan_text: text }),
    })
      .then(r => r.json())
      .then(() => loadPlan(state))
      .catch(() => {});
  });

  planPane.querySelector('.plan-complete-btn').addEventListener('click', () => {
    fetch('/api/plan/' + encodeURIComponent(name) + '/complete', { method: 'POST' })
      .then(r => r.json())
      .then(() => loadPlan(state))
      .catch(() => {});
  });

  // Minimize
  header.querySelector('.win-min').addEventListener('click', e => {
    e.stopPropagation();
    win.classList.toggle('minimized');
  });

  // Close
  header.querySelector('.win-close').addEventListener('click', e => {
    e.stopPropagation();
    closeWindow(state);
  });

  // Drag
  let dragging = false, dragOffX = 0, dragOffY = 0;
  header.addEventListener('mousedown', e => {
    if (e.target.closest('.win-actions')) return;
    dragging = true;
    win.style.zIndex = ++windowZ;
    const rect = win.getBoundingClientRect();
    dragOffX = e.clientX - rect.left;
    dragOffY = e.clientY - rect.top;
  });

  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    win.style.left = Math.max(0, e.clientX - dragOffX) + 'px';
    win.style.top = Math.max(0, e.clientY - dragOffY) + 'px';
  });

  document.addEventListener('mouseup', () => { dragging = false; });

  // Focus on click
  win.addEventListener('mousedown', () => { win.style.zIndex = ++windowZ; });

  // Load plan + monitor on open (monitor ready when tab clicked)
  loadPlan(state);
  loadMonitor(state);
  setTimeout(() => {
    const inp = win.querySelector('.win-chat-input input');
    if (inp) inp.focus();
  }, 80);

  // Monitor refresh interval
  state.monitorInterval = setInterval(() => {
    if (document.body.contains(win) && monitorPane.classList.contains('active') && !document.hidden) {
      loadMonitor(state);
    }
  }, 15000);

  // Live reasoning-trace feed (3s) while Monitor tab is open
  state.traceInterval = setInterval(() => {
    if (document.body.contains(win) && monitorPane.classList.contains('active') && !document.hidden) {
      refreshTraceFeed(state);
    }
  }, 3000);

  openWindows.set(name, state);
  updateCard(name);
}

// ===================== CLOSE WINDOW =====================
function closeWindow(state) {
  if (state.monitorInterval) clearInterval(state.monitorInterval);
  if (state.traceInterval) clearInterval(state.traceInterval);
  if (state.el.parentNode) state.el.parentNode.removeChild(state.el);
  openWindows.delete(state.name);
  updateCard(state.name);
}

// ===================== CHAT HELPERS =====================
function appendChatMsg(container, role, text, time) {
  const el = document.createElement('div');
  el.className = 'chat-msg ' + role;
  const label = role === 'user' ? 'You' : role === 'error' ? 'Error' : 'Agent';
  let body = '';
  if (typeof text === 'string' && text.includes('\n')) {
    body = '<pre>' + escapeHtml(text) + '</pre>';
  } else {
    body = '<span class="msg-text">' + escapeHtml(text) + '</span>';
  }
  el.innerHTML = '<span class="msg-label">' + label + '</span>' + body + '<span class="msg-time">' + (time || '') + '</span>';
  container.appendChild(el);
  container.scrollTop = container.scrollHeight;
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

function defaultCommands(name) {
  return [
    { label: 'Status', cmd: 'status', desc: 'Agent status report' },
    { label: 'Help', cmd: 'help', desc: 'List commands' },
  ];
}

function runAgentCommand(state, cmd) {
  if (!cmd) return;
  // Special: open another building window
  if (cmd.startsWith('__open:')) {
    const target = cmd.slice(7).trim();
    if (buildingMap[target]) openWindow(target);
    else {
      const msgContainer = state.el.querySelector('.win-chat-messages');
      appendChatMsg(msgContainer, 'error', 'Building not on map: ' + target, new Date().toLocaleTimeString());
    }
    return;
  }
  // Special: open external room
  if (cmd.startsWith('__url:')) {
    window.open(cmd.slice(6), '_blank', 'noopener');
    return;
  }

  const msgContainer = state.el.querySelector('.win-chat-messages');
  const now = new Date().toLocaleTimeString();
  state.chatHistory.push({ role: 'user', text: cmd, time: now });
  appendChatMsg(msgContainer, 'user', cmd, now);
  renderCommandButtons(msgContainer, state);

  fetch('/api/query', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent: state.name, query: cmd }),
  })
    .then(r => r.json())
    .then(data => {
      const rtime = new Date().toLocaleTimeString();
      const ok = data && data.ok;
      const role = ok ? 'agent' : 'error';
      const text = ok ? (data.result || 'ok') : (data && data.error) || 'request failed';
      const display = typeof text === 'object' ? JSON.stringify(text, null, 2) : String(text);
      state.chatHistory.push({ role, text: display, time: rtime });
      appendChatMsg(msgContainer, role, display, rtime);
      renderCommandButtons(msgContainer, state);
      // Auto-refresh monitor after command
      loadMonitor(state);
      msgContainer.scrollTop = msgContainer.scrollHeight;
    })
    .catch(e => {
      const etime = new Date().toLocaleTimeString();
      state.chatHistory.push({ role: 'error', text: e.message, time: etime });
      appendChatMsg(msgContainer, 'error', e.message, etime);
      renderCommandButtons(msgContainer, state);
    });
}

function promptForCommand(c) {
  return new Promise((resolve) => {
    if (!c.prompt) {
      resolve(c.cmd);
      return;
    }
    const value = window.prompt(c.prompt, (c.defaultValue || '').toString());
    if (value === null) {
      resolve(null);
      return;
    }
    const tmpl = c.template || c.cmd;
    resolve(tmpl.replace('{value}', value.trim()).replace('https://...', value.trim()));
  });
}

function renderCommandButtons(container, state) {
  const cmds = (COMMANDS[state.name] && COMMANDS[state.name].length)
    ? COMMANDS[state.name]
    : defaultCommands(state.name);
  const existing = container.querySelector('.cmd-btns');
  if (existing) existing.remove();

  const wrapper = document.createElement('div');
  wrapper.className = 'cmd-btns';
  // Room shortcut for web_check
  if (state.name === 'web_check') {
    const roomRow = document.createElement('div');
    roomRow.className = 'cmd-row';
    const roomBtn = document.createElement('button');
    roomBtn.className = 'cmd-btn accent';
    roomBtn.textContent = '🌐 Open Room UI';
    roomBtn.title = 'Open /room/webcheck/';
    roomBtn.addEventListener('click', () => window.open('/room/webcheck/', '_blank', 'noopener'));
    roomRow.appendChild(roomBtn);
    wrapper.appendChild(roomRow);
  }
  let cur = [];
  for (const c of cmds) {
    cur.push(c);
    if (cur.length >= 3) { addRow(wrapper, cur, state); cur = []; }
  }
  if (cur.length) addRow(wrapper, cur, state);
  container.appendChild(wrapper);
}

function addRow(wrapper, cmds, state) {
  const r = document.createElement('div');
  r.className = 'cmd-row';
  for (const c of cmds) {
    const btn = document.createElement('button');
    btn.className = 'cmd-btn' + (c.cmd && c.cmd.startsWith('__open:') ? ' linkish' : '');
    btn.title = c.desc || c.cmd;
    btn.textContent = c.label;
    btn.addEventListener('click', async () => {
      const cmd = await promptForCommand(c);
      if (cmd) runAgentCommand(state, cmd);
    });
    r.appendChild(btn);
  }
  wrapper.appendChild(r);
}

// ===================== PLAN =====================
function loadPlan(state) {
  fetch('/api/plan/' + encodeURIComponent(state.name))
    .then(r => r.json())
    .then(data => {
      const pane = state.el.querySelector('.win-pane[data-pane="plan"]');
      if (!pane) return;
      const textarea = pane.querySelector('textarea');
      const badge = pane.querySelector('.plan-status-badge');
      const meta = pane.querySelector('.plan-meta');
      if (data.plan_text) textarea.value = data.plan_text;
      badge.textContent = data.status || 'active';
      badge.className = 'plan-status-badge ' + (data.status || 'active');
      meta.textContent = data.created_at ? 'Created: ' + new Date(data.created_at).toLocaleDateString() : '';
    })
    .catch(() => {});
}

// ===================== MONITOR =====================
function loadMonitor(state) {
  fetch('/api/building/' + encodeURIComponent(state.name) + '/dashboard')
    .then(r => r.json())
    .then(data => {
      const pane = state.el.querySelector('.win-pane[data-pane="monitor"]');
      if (!pane) return;
      const monitor = pane.querySelector('.win-monitor');
      if (!monitor) return;

      // Use the per-building dashboard renderer
      monitor.innerHTML = dash(state.name, data);
    })
    .catch(() => {});
}

// ===================== TRACE FEED =====================
function refreshTraceFeed(state) {
  const pane = state.el.querySelector('.win-pane[data-pane="monitor"]');
  if (!pane) return;
  const feed = pane.querySelector('.trace-feed');
  if (!feed) return; // this building has no trace panel
  fetch('/api/agent/' + encodeURIComponent(state.name) + '/traces')
    .then(r => r.json())
    .then(data => {
      const traces = (data && data.traces) || [];
      feed.innerHTML = (typeof renderTraceHtml === 'function')
        ? renderTraceHtml(traces)
        : 'trace render unavailable';
    })
    .catch(() => {});
}

// ===================== SSE =====================
function updateCity(buildings) {
  if (!buildings || !buildings.length) return;
  const firstLoad = Object.keys(buildingMap).length === 0;
  for (const b of buildings) {
    buildingMap[b.name] = b;
  }
  renderGrid();

  // Update cards only — do NOT re-hit dashboards on every SSE tick
  for (const [name] of openWindows) {
    updateCard(name);
  }
}

function connectStream() {
  const es = new EventSource('/api/stream');
  es.onopen = () => { indicator.textContent = 'live'; indicator.className = 'connected'; };
  es.onerror = () => { indicator.textContent = 'reconnecting…'; indicator.className = 'disconnected'; };
  es.onmessage = evt => { try { updateCity(JSON.parse(evt.data)); } catch (e) {} };
}

// ===================== MEETING BAR (restored as simple header button) =====================
const meetBtn = document.createElement('button');
meetBtn.textContent = 'Hold Meeting';
meetBtn.style.cssText = 'font-size:9px;padding:3px 8px;background:#1a3a5a;color:#c8e1ff;border:none;border-radius:4px;cursor:pointer;text-transform:uppercase;letter-spacing:0.2px;';
meetBtn.addEventListener('click', async () => {
  meetBtn.textContent = 'Meeting...';
  try {
    await fetch('/api/meeting', { method: 'POST' });
  } catch (e) {}
  meetBtn.textContent = 'Hold Meeting';
});
document.querySelector('header > div').appendChild(meetBtn);

// ===================== START =====================
// Immediate load so buildings are clickable before SSE connects
fetch('/api/city')
  .then(r => r.json())
  .then(updateCity)
  .catch(() => {});
connectStream();
