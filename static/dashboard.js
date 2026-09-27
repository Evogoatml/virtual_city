/**
 * dashboard.js — Per-building full-scale dashboard renderers.
 *
 * Each renderer receives a container element and a data payload from
 * /api/building/<name>/dashboard.  Pure DOM, no dependencies.
 */

function dash(name, data) {
  const fn = DASHBOARDS[name] || DASHBOARDS._default;
  try {
    return fn(data || {});
  } catch (e) {
    return '<div class="hint">Dashboard error for ' + escapeHtml((data && data.name) || name) + ': ' + escapeHtml(e.message) + '</div>';
  }
}

const DASHBOARDS = {};

// ── Default fallback ────────────────────────────────────────────────
DASHBOARDS._default = function (d) {
  const rp = (d && d.report) || {};
  const keys = Object.keys(rp);
  let h = '<div class="dash">';
  h += '<div class="dash-row">';
  h += card('Agent', escapeHtml((d && d.name) || '-'), '');
  h += card('Subject', escapeHtml((d && d.subject) || '-'), '');
  h += card('Keys', String(keys.length), '');
  h += '</div>';
  if (keys.length) {
    h += '<div class="dash-card"><h4>Report</h4><pre class="dash-json">' + escapeHtml(JSON.stringify(rp, null, 2)) + '</pre></div>';
  }
  h += dashEvents(d || {});
  h += dashTrace(d || {});
  h += '</div>';
  return h;
};

// ── Crypto Trading ──────────────────────────────────────────────────
DASHBOARDS.crypto_trading = function dashCrypto(d) {
  const rp = d.report || {};
  const positions = d.positions || [];
  const openP = rp.open_positions || 0;
  const pnl = d.total_pnl || rp.pnl || 0;
  const trades = d.total_trades || rp.total_trades || 0;

  let h = '<div class="dash">';
  h += '<div class="dash-row">';
  h += card('Open Positions', String(openP), openP > 0 ? 'yellow' : '');
  h += card('Total PnL', '$' + fmtNum(pnl), pnl >= 0 ? 'green' : 'red');
  h += card('Total Trades', String(trades), '');
  h += '</div>';

  if (positions.length) {
    h += '<div class="dash-card"><h4>Open Positions</h4><div class="dash-table-wrap">';
    h += '<table class="dash-table"><thead><tr><th>Symbol</th><th>Side</th><th>Size</th><th>Entry</th><th>Current</th><th>PnL</th></tr></thead><tbody>';
    for (const p of positions) {
      const pnlVal = p.pnl || 0;
      h += '<tr><td>' + esc(p.symbol || p.market || '-') + '</td><td>' + (p.side || 'long') + '</td>'
        + '<td>' + fmtNum(p.size || p.quantity || 0) + '</td><td>$' + fmtNum(p.entry_price || 0) + '</td>'
        + '<td>$' + fmtNum(p.current_price || 0) + '</td>'
        + '<td class="' + (pnlVal >= 0 ? 'green' : 'red') + '">$' + fmtNum(pnlVal) + '</td></tr>';
    }
    h += '</tbody></table></div></div>';
  }

  h += dashEvents(d);
  h += '</div>';
  return h;
};

// ── Market Data ─────────────────────────────────────────────────────
DASHBOARDS.market_data = function dashMarket(d) {
  const rp = d.report || {};
  const prices = d.prices || [];
  const running = rp.running ? true : false;

  let h = '<div class="dash">';
  h += '<div class="dash-row">';
  h += card('Engine', running ? 'ON' : 'OFF', running ? 'green' : 'red');
  h += card('Monitored', String(rp.monitored_pairs || prices.length || 0), '');
  h += '</div>';

  if (prices.length) {
    h += '<div class="dash-card"><h4>Prices</h4><div class="dash-table-wrap">';
    h += '<table class="dash-table"><thead><tr><th>Pair</th><th>Bid</th><th>Ask</th><th>Spread</th><th>Updated</th></tr></thead><tbody>';
    for (const p of prices) {
      const bid = p.bid || p.price || 0;
      const ask = p.ask || p.price || 0;
      const spread = ask > 0 ? ((ask - bid) / ask * 100).toFixed(3) + '%' : '-';
      h += '<tr><td>' + esc(p.symbol || p.pair || '-') + '</td><td>$' + fmtNum(bid) + '</td><td>$' + fmtNum(ask) + '</td><td>' + spread + '</td><td>' + (p.updated_at || p.timestamp || '').slice(0, 10) + '</td></tr>';
    }
    h += '</tbody></table></div></div>';
  }

  h += dashEvents(d);
  h += '</div>';
  return h;
};

// ── Shopify ─────────────────────────────────────────────────────────
DASHBOARDS.shopify = function dashShopify(d) {
  const rp = d.report || {};
  const orders = d.orders || [];
  const top = d.top_products || [];
  const rev = rp.revenue || 0;
  const profit = rp.profit || 0;

  let h = '<div class="dash">';
  h += '<div class="dash-row">';
  h += card('Revenue', '$' + fmtNum(rev), rev > 0 ? 'green' : '');
  h += card('Profit', '$' + fmtNum(profit), profit > 0 ? 'green' : 'red');
  h += card('Orders', String(rp.orders || orders.length), '');
  h += '</div>';

  if (top.length) {
    h += '<div class="dash-card"><h4>Top Products</h4><div class="dash-table-wrap">';
    h += '<table class="dash-table"><thead><tr><th>Product</th><th>Revenue</th></tr></thead><tbody>';
    for (const t of top) {
      h += '<tr><td>' + esc(t.product) + '</td><td>$' + fmtNum(t.rev) + '</td></tr>';
    }
    h += '</tbody></table></div></div>';
  }

  if (orders.length) {
    h += '<div class="dash-card"><h4>Recent Orders</h4><div class="dash-table-wrap">';
    h += '<table class="dash-table"><thead><tr><th>Product</th><th>Revenue</th><th>Cost</th><th>Profit</th><th>Type</th></tr></thead><tbody>';
    for (const o of orders) {
      const p = (o.revenue || 0) - (o.cost || 0);
      h += '<tr><td>' + esc(o.product) + '</td><td>$' + fmtNum(o.revenue || 0) + '</td><td>$' + fmtNum(o.cost || 0) + '</td><td class="' + (p >= 0 ? 'green' : 'red') + '">$' + fmtNum(p) + '</td><td>' + (o.type || '-') + '</td></tr>';
    }
    h += '</tbody></table></div></div>';
  }

  h += dashEvents(d);
  h += dashTrace(d);
  h += '</div>';
  return h;
};

// ── Product Flipping ────────────────────────────────────────────────
DASHBOARDS.product_flipping = function dashFlip(d) {
  const rp = d.report || {};
  const items = d.inventory || [];

  let h = '<div class="dash">';
  h += '<div class="dash-row">';
  h += card('Inventory', String(rp.open_inventory || items.length), '');
  h += card('Avg Margin', rp.avg_margin_pct ? rp.avg_margin_pct + '%' : '-', '');
  h += card('Total Margin', '$' + fmtNum(rp.total_margin_usd || 0), 'green');
  h += '</div>';

  if (items.length) {
    h += '<div class="dash-card"><h4>Inventory</h4><div class="dash-table-wrap">';
    h += '<table class="dash-table"><thead><tr><th>Item</th><th>Cost</th><th>Target</th><th>Status</th><th>Margin</th></tr></thead><tbody>';
    for (const i of items) {
      const margin = (i.target_price || 0) - (i.cost_price || 0);
      h += '<tr><td>' + esc(i.name || i.item || '-') + '</td><td>$' + fmtNum(i.cost_price || 0) + '</td><td>$' + fmtNum(i.target_price || 0) + '</td><td>' + (i.status || 'open') + '</td><td class="' + (margin >= 0 ? 'green' : 'red') + '">$' + fmtNum(margin) + '</td></tr>';
    }
    h += '</tbody></table></div></div>';
  }

  h += dashEvents(d);
  h += '</div>';
  return h;
};

// ── Social Affiliates ───────────────────────────────────────────────
DASHBOARDS.social_affiliates = function dashAffil(d) {
  const rp = d.report || {};
  const camps = d.campaigns || [];

  let h = '<div class="dash">';
  h += '<div class="dash-row">';
  h += card('Campaigns', String(rp.campaigns || camps.length), '');
  h += card('Clicks', String(rp.total_clicks || 0), '');
  h += card('Revenue', '$' + fmtNum(rp.revenue || 0), 'green');
  h += '</div>';

  if (camps.length) {
    h += '<div class="dash-card"><h4>Campaigns</h4><div class="dash-table-wrap">';
    h += '<table class="dash-table"><thead><tr><th>Name</th><th>Platform</th><th>Status</th><th>Clicks</th><th>Conversions</th><th>Revenue</th></tr></thead><tbody>';
    for (const c of camps) {
      h += '<tr><td>' + esc(c.campaign_name || '-') + '</td><td>' + esc(c.platform || '-') + '</td><td>' + (c.status || 'active') + '</td><td>' + (c.clicks || 0) + '</td><td>' + (c.conversions || 0) + '</td><td>$' + fmtNum(c.revenue || 0) + '</td></tr>';
    }
    h += '</tbody></table></div></div>';
  }

  h += dashEvents(d);
  h += '</div>';
  return h;
};

// ── Sourcing Research ───────────────────────────────────────────────
DASHBOARDS.sourcing_research = function dashSourcing(d) {
  const rp = d.report || {};
  const leads = d.leads || [];

  let h = '<div class="dash">';
  h += '<div class="dash-row">';
  h += card('Open Leads', String(rp.open_leads || leads.length), '');
  h += card('Avg Score', (rp.avg_open_score || 0).toFixed(1), 'gold');
  h += card('Success Rate', (rp.success_rate || 0) + '%', '');
  h += '</div>';

  if (leads.length) {
    h += '<div class="dash-card"><h4>Leads</h4><div class="dash-table-wrap">';
    h += '<table class="dash-table"><thead><tr><th>Product</th><th>Category</th><th>Score</th><th>Status</th><th>Created</th></tr></thead><tbody>';
    for (const l of leads) {
      h += '<tr><td>' + esc(l.product || '-') + '</td><td>' + esc(l.category || '-') + '</td><td><span class="score-badge">' + (l.score || 0) + '</span></td><td>' + (l.status || 'open') + '</td><td>' + (l.created_at || '').slice(0, 10) + '</td></tr>';
    }
    h += '</tbody></table></div></div>';
  }

  h += dashEvents(d);
  h += '</div>';
  return h;
};

// ── Finance Treasury ────────────────────────────────────────────────
DASHBOARDS.finance_treasury = function dashFinance(d) {
  const rp = d.report || {};
  const ledger = d.ledger || [];

  let h = '<div class="dash">';
  h += '<div class="dash-row">';
  h += card('Balance', '$' + fmtNum(rp.grand_total_usd || 0), 'gold');
  h += card('Total Income', '$' + fmtNum(rp.total_income || 0), 'green');
  h += card('Total Expenses', '$' + fmtNum(rp.total_expenses || 0), 'red');
  h += '</div>';

  if (ledger.length) {
    h += '<div class="dash-card"><h4>Ledger</h4><div class="dash-table-wrap">';
    h += '<table class="dash-table"><thead><tr><th>Category</th><th>Type</th><th>Amount</th><th>Note</th><th>Date</th></tr></thead><tbody>';
    for (const e of ledger) {
      const amt = e.amount || 0;
      h += '<tr><td>' + esc(e.category || '-') + '</td><td>' + (amt >= 0 ? 'credit' : 'debit') + '</td><td class="' + (amt >= 0 ? 'green' : 'red') + '">$' + fmtNum(Math.abs(amt)) + '</td><td>' + esc(e.note || '') + '</td><td>' + (e.created_at || '').slice(0, 10) + '</td></tr>';
    }
    h += '</tbody></table></div></div>';
  }

  h += dashEvents(d);
  h += '</div>';
  return h;
};

// ── City Hall ───────────────────────────────────────────────────────
DASHBOARDS.city_hall = function dashHall(d) {
  const rp = d.report || {};
  const meetings = d.meetings || [];

  let h = '<div class="dash">';
  h += '<div class="dash-row">';
  h += card('Meetings Held', String(rp.meetings_held || 0), '');
  h += card('Buildings', String(d.total_buildings || 17), '');
  h += card('Role', String(rp.role || 'CEO'), '');
  h += '</div>';

  if (meetings.length) {
    h += '<div class="dash-card"><h4>Meeting History</h4><div class="dash-table-wrap">';
    h += '<table class="dash-table"><thead><tr><th>#</th><th>Summary</th><th>Date</th></tr></thead><tbody>';
    for (const m of meetings) {
      const summary = (m.summary || '').slice(0, 60);
      h += '<tr><td>' + (m.id || '-') + '</td><td>' + esc(summary) + '</td><td>' + (m.held_at || '').slice(0, 10) + '</td></tr>';
    }
    h += '</tbody></table></div></div>';
  }

  h += dashEvents(d);
  h += '</div>';
  return h;
};

// ── Signal ─────────────────────────────────────────────────────────
DASHBOARDS.signal = function dashSignal(d) {
  const rp = d.report || {};
  const watches = rp.watches || [];
  const alerts = d.alerts || d.report?.alerts || [];

  let h = '<div class="dash">';
  h += '<div class="dash-row">';
  h += card('Active Watches', String(rp.active_watches || 0), rp.active_watches > 0 ? 'green' : '');
  h += card('Unread Alerts', String(rp.unread_alerts || 0), rp.unread_alerts > 0 ? 'yellow' : '');
  h += card('Last Change', rp.last_change ? rp.last_change.slice(0,16) : '-', '');
  h += '</div>';

  if (alerts.length) {
    h += '<div class="dash-card"><h4>Recent Alerts</h4><div class="dash-table-wrap">';
    h += '<table class="dash-table"><thead><tr><th>Label</th><th>URL</th><th>Snippet</th><th>Time</th></tr></thead><tbody>';
    for (const a of alerts.slice(0, 15)) {
      const snippet = (a.content_snippet || '').slice(0, 50);
      h += '<tr><td>' + esc(a.label || '-') + '</td><td class="mono">' + esc((a.url || '').slice(0, 35)) + '</td><td>' + esc(snippet) + '</td><td>' + (a.detected_at || '').slice(0, 10) + '</td></tr>';
    }
    h += '</tbody></table></div></div>';
  }

  if (watches.length) {
    h += '<div class="dash-card"><h4>Watches</h4><div class="dash-table-wrap">';
    h += '<table class="dash-table"><thead><tr><th>Label</th><th>Interval</th><th>Last Checked</th><th>Status</th></tr></thead><tbody>';
    for (const w of watches) {
      h += '<tr><td>' + esc(w.label || '-') + '</td><td>' + (w.interval_min || 15) + 'm</td><td>' + (w.last_checked || 'never').slice(0, 16) + '</td><td><span class="status-badge ' + (w.status || 'active') + '">' + (w.status || 'active') + '</span></td></tr>';
    }
    h += '</tbody></table></div></div>';
  }

  h += dashEvents(d);
  h += '</div>';
  return h;
};

// ── Finance Building (hub) ──────────────────────────────────────────
DASHBOARDS.finance_building = function dashFinanceHub(d) {
  let h = '<div class="dash">';
  h += '<div class="dash-row">';
  const ct = d.crypto_trading || {};
  const md = d.market_data || {};
  const ft = d.finance_treasury || {};
  h += card('Crypto PnL', '$' + fmtNum(ct.pnl || 0), (ct.pnl || 0) >= 0 ? 'green' : 'red');
  h += card('Market Pairs', String(md.monitored_pairs || 0), '');
  h += card('Treasury', '$' + fmtNum(ft.grand_total_usd || 0), 'gold');
  h += '</div>';
  h += '<div class="dash-row">';
  h += card('Open Pos', String(ct.open_positions || 0), (ct.open_positions || 0) > 0 ? 'yellow' : '');
  h += '</div>';
  h += dashEvents(d);
  h += '</div>';
  return h;
};

// ── Media Building (hub) ────────────────────────────────────────────
DASHBOARDS.media_building = function dashMediaHub(d) {
  const sa = d.social_affiliates || {};
  let h = '<div class="dash">';
  h += '<div class="dash-row">';
  h += card('Campaigns', String(sa.campaigns || 0), '');
  h += card('Clicks', String(sa.total_clicks || 0), '');
  h += card('Revenue', '$' + fmtNum(sa.revenue || 0), 'green');
  h += '</div>';
  h += dashEvents(d);
  h += '</div>';
  return h;
};

// ── Research Building (hub) ─────────────────────────────────────────
DASHBOARDS.research_building = function dashResearchHub(d) {
  const sr = d.sourcing_research || {};
  const wc = d.web_check || {};
  const ss = d.supply_scout || {};
  const pf = d.product_flipping || {};
  const sig = d.signal || {};
  let h = '<div class="dash">';
  h += '<div class="dash-row">';
  h += card('Open Leads', String(sr.open_leads || d.open_leads || 0), '');
  h += card('Avg Score', String(sr.avg_score || d.avg_open_score || 0), '');
  h += card('Supply Scout', ss.subject || 'active', 'gold');
  h += '</div>';
  h += '<div class="dash-row">';
  h += card('Web-Check', (wc.service_running ? 'ONLINE' : 'OFFLINE'), wc.service_running ? 'green' : 'red');
  h += card('Scans', String(wc.scans_total || 0), '');
  h += card('Flip Items', String(pf.inventory_count || 0), pf.inventory_count > 0 ? 'yellow' : '');
  h += card('Signals', String(sig.watches || 0), '');
  h += '</div>';
  h += '<div class="dash-card"><h4>Departments</h4><div class="dash-actions">';
  h += '<span class="hint">Enter from Chat: Supply Scout / Enter Sourcing / Enter Flipping / Enter Web-Check / Enter Signal</span>';
  h += '</div></div>';
  h += dashEvents(d);
  h += '</div>';
  return h;
};


// ── Controll Panel (Command Center) ──────────────────────────────────
DASHBOARDS.controll_panel = function dashControll(d) {
  const rp = d.report || {};
  const metrics = rp.metrics || {};
  const routes = d.pipeline_routes || [];
  const alerts = d.alerts || [];

  let h = '<div class="dash">';
  h += '<div class="dash-row">';
  h += card('Buildings', String(metrics.active_buildings || 0), metrics.error_buildings > 0 ? 'red' : 'green');
  h += card('Errors', String(metrics.error_buildings || 0), metrics.error_buildings > 0 ? 'red' : '');
  h += card('Events/hr', String(metrics.event_rate_last_hour || 0), '');
  h += '</div>';
  h += '<div class="dash-row">';
  h += card('Route Logs', String(metrics.route_log_entries || 0), '');
  h += card('Alerts', String(alerts.filter(function(a){return !a.acknowledged;}).length), alerts.some(function(a){return !a.acknowledged;}) ? 'yellow' : '');
  h += card('Mode', 'COMMAND', 'gold');
  h += '</div>';

  if (routes.length) {
    h += '<div class="dash-card"><h4>Pipeline Routes</h4><div class="dash-table-wrap">';
    h += '<table class="dash-table"><thead><tr><th>From</th><th>To</th><th>Event</th><th>Events</th></tr></thead><tbody>';
    for (var ri = 0; ri < routes.length; ri++) {
      var r = routes[ri];
      h += '<tr><td>' + esc(r.from || '-') + '</td><td>' + esc(r.to || '-') + '</td><td>' + esc(r.event || '-') + '</td><td>' + (r.total_events || 0) + '</td></tr>';
    }
    h += '</tbody></table></div></div>';
  }

  var subs = d.subscriptions || [];
  if (subs.length) {
    h += '<div class="dash-card"><h4>EventBus Wiring</h4><div class="dash-table-wrap">';
    h += '<table class="dash-table"><thead><tr><th>Subscriber</th><th>Publisher</th><th>Event</th></tr></thead><tbody>';
    for (var si = 0; si < subs.length && si < 20; si++) {
      var s = subs[si];
      h += '<tr><td>' + esc(s.subscriber_name || '-') + '</td><td>' + esc(s.publisher_name || '-') + '</td><td>' + esc(s.event_type || '*') + '</td></tr>';
    }
    h += '</tbody></table></div></div>';
  }

  h += dashEvents(d);
  h += dashTrace(d);
  h += '</div>';
  return h;
};

// ── Neural Index ─────────────────────────────────────────────────────
DASHBOARDS.neural_index = function dashNeural(d) {
  var stats = d.stats || {};
  var h = '<div class="dash">';
  h += '<div class="dash-row">';
  h += card('Files Indexed', String(stats.indexed_files || 0), '');
  h += card('Knowledge Nodes', String(stats.knowledge_nodes || 0), '');
  h += card('Folder Agents', String(stats.agents_generated || 0), '');
  h += '</div>';

  var agents = d.agents || [];
  if (agents.length) {
    h += '<div class="dash-card"><h4>Folder Agents</h4><div class="dash-table-wrap">';
    h += '<table class="dash-table"><thead><tr><th>Agent ID</th><th>Folder</th><th>Updated</th></tr></thead><tbody>';
    for (var ai = 0; ai < agents.length && ai < 15; ai++) {
      var a = agents[ai];
      h += '<tr><td class="mono">' + esc(a.agent_id || '-') + '</td><td>' + esc((a.folder || '').slice(0, 40)) + '</td><td>' + (a.last_updated || '').slice(0, 16) + '</td></tr>';
    }
    h += '</tbody></table></div></div>';
  }

  var files = d.indexed_files || [];
  if (files.length) {
    h += '<div class="dash-card"><h4>Recently Indexed</h4><div class="dash-table-wrap">';
    h += '<table class="dash-table"><thead><tr><th>File</th><th>Size</th><th>Indexed</th></tr></thead><tbody>';
    for (var fi = 0; fi < files.length && fi < 15; fi++) {
      var f = files[fi];
      var fp = f.filepath || '-';
      var rel = fp.length > 50 ? '...' + fp.slice(-47) : fp;
      h += '<tr><td class="mono">' + esc(rel) + '</td><td>' + (f.size || 0) + 'B</td><td>' + (f.indexed_at || '').slice(0, 16) + '</td></tr>';
    }
    h += '</tbody></table></div></div>';
  }

  h += dashEvents(d);
  h += '</div>';
  return h;
};


// ── Scraper ─────────────────────────────────────────────────────────
DASHBOARDS.scraper = function dashScraper(d) {
  const rp = d.report || {};
  const results = d.results_list || [];

  let h = '<div class="dash">';
  h += '<div class="dash-row">';
  h += card('Total Scrapes', String(rp.total_scrapes || 0), '');
  h += card('Pending', String(rp.queue_pending || 0), rp.queue_pending > 0 ? 'yellow' : '');
  h += card('Errors', String(rp.queue_errors || 0), rp.queue_errors > 0 ? 'red' : '');
  h += '</div>';
  h += '<div class="dash-row">';
  h += card('Done', String(rp.queue_done || 0), 'green');
  h += card('Robots', String(rp.robots || 0), '');
  h += '</div>';

  if (results.length) {
    h += '<div class="dash-card"><h4>Recent Results</h4><div class="dash-table-wrap">';
    h += '<table class="dash-table"><thead><tr><th>Title</th><th>URL</th><th>Status</th><th>Tier</th><th>Size</th><th>Time</th></tr></thead><tbody>';
    for (const r of results) {
      h += '<tr><td>' + esc((r.title || '').slice(0, 30)) + '</td><td class="mono">' + esc((r.url || '').slice(0, 30)) + '</td><td>' + (r.status_code || '-') + '</td><td>T' + (r.tier_used || '?') + '</td><td>' + ((r.bytes_fetched || 0) / 1024).toFixed(1) + 'kb</td><td>' + (r.fetch_ms || 0) + 'ms</td></tr>';
    }
    h += '</tbody></table></div></div>';
  }

  h += dashEvents(d);
  h += '</div>';
  return h;
};


// ═════════════════════════════════════════════════════════════════════
// Helpers
// ═════════════════════════════════════════════════════════════════════

function card(label, value, cls) {
  return '<div class="monitor-card"><h4>' + escapeHtml(label) + '</h4><div class="value ' + (cls || '') + '">' + value + '</div></div>';
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

var esc = escapeHtml;

function fmtNum(n) {
  if (n == null || isNaN(n)) return '0';
  return Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}




// ── Web Check room ──────────────────────────────────────────────────
DASHBOARDS.web_check = function dashWebCheck(d) {
  const rp = d.report || {};
  const svc = d.service || {};
  const scans = d.scans || rp.recent || [];
  const running = !!(svc.running || rp.service_running);

  let h = '<div class="dash">';
  h += '<div class="dash-row">';
  h += card('Service', running ? 'ONLINE' : 'OFFLINE', running ? 'green' : 'red');
  h += card('Scans', String(rp.scans_total || scans.length || 0), '');
  h += card('Built', (svc.built || rp.built) ? 'YES' : 'NO', (svc.built || rp.built) ? 'green' : 'yellow');
  h += '</div>';

  h += '<div class="dash-card"><h4>Room</h4>';
  h += '<p class="hint">Open the full Web-Check UI inside the city room.</p>';
  h += '<div class="dash-actions">';
  h += '<a class="dash-btn" href="/room/webcheck/" target="_blank" rel="noopener">Open Room ↗</a>';
  h += '<a class="dash-btn secondary" href="' + esc(svc.url || rp.direct_url || 'http://127.0.0.1:3000') + '" target="_blank" rel="noopener">Direct :3000 ↗</a>';
  h += '</div></div>';

  if (scans.length) {
    h += '<div class="dash-card"><h4>Recent Scans</h4><div class="dash-table-wrap">';
    h += '<table class="dash-table"><thead><tr><th>ID</th><th>Target</th><th>Label</th><th>Status</th><th>When</th></tr></thead><tbody>';
    for (const s of scans.slice(0, 15)) {
      h += '<tr><td>' + (s.id || '-') + '</td><td class="mono">' + esc((s.target_url || s.target || '').slice(0, 40)) + '</td><td>' + esc(s.label || '-') + '</td><td><span class="status-badge ' + (s.status || '') + '">' + esc(s.status || '-') + '</span></td><td>' + esc((s.created_at || s.finished_at || '').slice(0, 16)) + '</td></tr>';
    }
    h += '</tbody></table></div></div>';
  }

  h += dashEvents(d);
  h += '</div>';
  return h;
};

function dashEvents(d) {
  const evts = d.events || [];
  if (!evts.length) return '';
  let h = '<div class="dash-card"><h4>Recent Activity</h4>';
  for (const e of evts.slice(0, 10)) {
    h += '<div class="monitor-event"><span class="ts">' + (e.timestamp || '').slice(0, 16) + '</span> <span class="type">' + escapeHtml(e.type) + '</span> — ' + escapeHtml(e.message) + '</div>';
  }
  h += '</div>';
  return h;
}

// ── Reasoning Trace feed (CTMS-style <tag:type:ctmsact>) ──────────────
function traceClass(glyph) {
  if (glyph === '♢') return 't-think';
  if (glyph === '⊨') return 't-ok';
  if (glyph === '↺') return 't-warn';
  if (glyph === '⋔') return 't-branch';
  if (glyph === '↑') return 't-up';
  if (glyph === '⍟') return 't-meta';
  return '';
}

function renderTraceHtml(traces) {
  if (!traces || !traces.length) return '<div class="hint">No trace activity yet.</div>';
  let h = '';
  for (const t of traces.slice(0, 40)) {
    h += '<div class="trace-line ' + traceClass(t.ctmsact) + '">'
      + '<span class="trace-tag">' + esc(t.tag) + ':' + esc(t.type) + ':' + esc(t.ctmsact) + '</span> '
      + '<span class="trace-content">' + esc(t.content) + '</span>'
      + '<span class="trace-time">' + (t.created_at || '').slice(11, 19) + '</span>'
      + '</div>';
  }
  return h;
}

function dashTrace(d) {
  const traces = d.traces || [];
  if (!traces.length) return '';
  return '<div class="dash-card"><h4>Reasoning Trace</h4><div class="trace-feed">' + renderTraceHtml(traces) + '</div></div>';
}