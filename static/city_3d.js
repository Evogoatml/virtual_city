import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';

const container = document.getElementById('canvas-container');
const loadingScreen = document.getElementById('loading-screen');
const indicator = document.getElementById('connection-indicator');

const agentTitle = document.getElementById('agent-title');
const agentDistrict = document.getElementById('agent-district');
const chatMessages = document.getElementById('chat-messages');

const chatAgentSelect = document.getElementById('chat-agent');
const chatInput = document.getElementById('chat-input');
const chatSend = document.getElementById('chat-send');
const workspaceContent = document.getElementById('workspace-content');
const reportContent = document.getElementById('report-content');
const reportEvents = document.getElementById('report-events');
const meetingOutput = document.getElementById('meeting-output');

// --- Scene ---
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x070b12);
scene.fog = new THREE.FogExp2(0x070b12, 0.012);

const camera = new THREE.PerspectiveCamera(40, container.clientWidth / container.clientHeight, 0.1, 100);
camera.position.set(28, 22, 28);
camera.lookAt(0, 0, 0);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(container.clientWidth, container.clientHeight);
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;
container.appendChild(renderer.domElement);

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(container.clientWidth, container.clientHeight), 0.3, 0.2, 0.1);
composer.addPass(bloom);

const labelRenderer = new CSS2DRenderer();
labelRenderer.setSize(container.clientWidth, container.clientHeight);
labelRenderer.domElement.style.position = 'absolute';
labelRenderer.domElement.style.top = '0';
labelRenderer.domElement.style.left = '0';
labelRenderer.domElement.style.pointerEvents = 'none';
container.appendChild(labelRenderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true; controls.dampingFactor = 0.08;
controls.minDistance = 10; controls.maxDistance = 55;
controls.maxPolarAngle = Math.PI / 2.15;
controls.target.set(0, 3, 0); controls.update();

// --- Lights ---
scene.add(new THREE.AmbientLight(0x223355, 0.3));
scene.add(new THREE.HemisphereLight(0x8899cc, 0x443322, 0.6));
const sun = new THREE.DirectionalLight(0xffeedd, 2.0);
sun.position.set(18, 30, 12);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.camera.near = 1; sun.shadow.camera.far = 60;
sun.shadow.camera.left = -25; sun.shadow.camera.right = 25;
sun.shadow.camera.top = 25; sun.shadow.camera.bottom = -25;
scene.add(sun);
const fill = new THREE.DirectionalLight(0x4488ff, 0.3);
fill.position.set(-15, 10, -15);
scene.add(fill);

// --- Ground + Roads ---
function createGround() {
  const g = new THREE.Group();
  const groundMat = new THREE.MeshStandardMaterial({ color: 0x0d1520, roughness: 0.9 });
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(55, 40), groundMat);
  ground.rotation.x = -Math.PI / 2; ground.position.set(0, -0.05, 0); ground.receiveShadow = true;
  g.add(ground);
  const roadMat = new THREE.MeshStandardMaterial({ color: 0x1a2a3a, roughness: 0.8 });
  const markMat = new THREE.MeshStandardMaterial({ color: 0x2a3a4a });
  for (let z of [-4, 4]) {
    const r = new THREE.Mesh(new THREE.PlaneGeometry(42, 1.8), roadMat);
    r.rotation.x = -Math.PI / 2; r.position.set(0, 0, z); r.receiveShadow = true; g.add(r);
    const m = new THREE.Mesh(new THREE.PlaneGeometry(40, 0.08), markMat);
    m.rotation.x = -Math.PI / 2; m.position.set(0, 0.01, z); g.add(m);
  }
  for (let x of [-12, -4, 4, 12]) {
    const r = new THREE.Mesh(new THREE.PlaneGeometry(1.8, 22), roadMat);
    r.rotation.x = -Math.PI / 2; r.position.set(x, 0, 0); r.receiveShadow = true; g.add(r);
    const m = new THREE.Mesh(new THREE.PlaneGeometry(0.08, 20), markMat);
    m.rotation.x = -Math.PI / 2; m.position.set(x, 0.01, 0); g.add(m);
  }
  return g;
}
scene.add(createGround());

// --- Trees ---
function createTree(x, z) {
  const g = new THREE.Group();
  const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.18, 1.2, 6),
    new THREE.MeshStandardMaterial({ color: 0x3d2b1f, roughness: 0.9 }));
  trunk.position.y = 0.6; trunk.castShadow = true; g.add(trunk);
  const leafMat = new THREE.MeshStandardMaterial({
    color: [0x1a3a1a, 0x2a4a2a, 0x0d2d0d][Math.floor(Math.random() * 3)], roughness: 0.9
  });
  const crown = new THREE.Mesh(new THREE.SphereGeometry(0.6, 6, 6), leafMat);
  crown.position.y = 1.5 + Math.random() * 0.3; crown.scale.y = 0.8 + Math.random() * 0.3;
  crown.castShadow = true; g.add(crown);
  g.position.set(x, 0, z); return g;
}
(function addTrees() {
  const pts = [];
  for (let z of [-4, 4]) for (let x = -16; x <= 16; x += 2.5) { if (Math.abs(x % 8) < 1) continue; if (Math.random() > 0.5) pts.push([x + (Math.random() - 0.5) * 0.5, z + 1.4]); }
  for (let x of [-12, -4, 4, 12]) for (let z = -6; z <= 6; z += 2.5) { if (Math.abs(z % 4) < 1) continue; if (Math.random() > 0.5) pts.push([x + 1.4, z + (Math.random() - 0.5) * 0.5]); }
  for (const [x, z] of pts) scene.add(createTree(x, z));
})();

// --- Building texture generation ---
function hash(name) { let h = 0; for (let i = 0; i < name.length; i++) h = ((h << 5) - h) + name.charCodeAt(i) | 0; return Math.abs(h); }

function createFacadeTexture(colorHex, name, w, h, litRatio) {
  const cw = 256, ch = 512;
  const canvas = document.createElement('canvas'); canvas.width = cw; canvas.height = ch;
  const ctx = canvas.getContext('2d');
  const base = new THREE.Color(colorHex);
  ctx.fillStyle = `#${base.getHexString()}`; ctx.fillRect(0, 0, cw, ch);
  const grad = ctx.createLinearGradient(0, 0, 0, ch);
  grad.addColorStop(0, 'rgba(0,0,0,0.15)'); grad.addColorStop(0.05, 'rgba(0,0,0,0.05)');
  grad.addColorStop(0.95, 'rgba(0,0,0,0.05)'); grad.addColorStop(1, 'rgba(0,0,0,0.2)');
  ctx.fillStyle = grad; ctx.fillRect(0, 0, cw, ch);
  const hh = hash(name); const cols = 6, rows = 8; const margin = 12;
  const winW = (cw - 2 * margin - (cols - 1) * 3) / cols;
  const winH = (ch - 2 * margin - (rows - 1) * 3) / rows;
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
    const lit = ((hh + r * 7 + c * 13 + Math.floor(w * h)) % 5) > (1 - litRatio * 5);
    const wx = margin + c * (winW + 3); const wy = margin + r * (winH + 3);
    if (lit) {
      const bright = 0.7 + ((hh + r * 11 + c * 17) % 3) * 0.15;
      ctx.fillStyle = `rgba(255, 213, 79, ${bright})`;
      ctx.shadowColor = 'rgba(255, 200, 50, 0.4)'; ctx.shadowBlur = 6;
      ctx.fillRect(wx, wy, winW, winH); ctx.shadowBlur = 0;
    } else { ctx.fillStyle = `rgba(20, 35, 50, 0.8)`; ctx.fillRect(wx, wy, winW, winH); }
  }
  const dl = ctx.createRadialGradient(cw/2, ch-30, 2, cw/2, ch-20, 20);
  dl.addColorStop(0, 'rgba(255,180,80,0.3)'); dl.addColorStop(1, 'rgba(255,180,80,0)');
  ctx.fillStyle = dl; ctx.fillRect(cw/2-20, ch-40, 40, 30);
  const tex = new THREE.CanvasTexture(canvas); return tex;
}

// --- Building creation ---
const STATUS_COLORS = { idle: 0x4caf50, working: 0xffb300, error: 0xe53935 };
const buildingMap = new Map();
let selectedName = null;

function makeRoof(w, d, h) {
  const hw = w/2, hd = d/2;
  const geom = new THREE.BufferGeometry();
  geom.setAttribute('position', new THREE.BufferAttribute(new Float32Array([
    -hw,0,hd, 0,h,0, hw,0,hd, -hw,0,-hd, hw,0,-hd, 0,h,0,
    -hw,0,-hd, -hw,0,hd, 0,h,0, hw,0,hd, hw,0,-hd, 0,h,0
  ]), 3));
  geom.setIndex([0,1,2,3,4,5,6,7,8,9,10,11]);
  geom.computeVertexNormals(); return geom;
}

function createBuilding(data) {
  const sc = 0.05, cx = 400, cy = 240;
  const px = (data.x - cx) * sc, pz = (data.y - cy) * sc;
  const w = Math.max(data.w * sc, 3), d = Math.max(data.h * sc, 3);
  const isCEO = data.name === 'city_hall';
  const h = isCEO ? 6.5 : 3 + (hash(data.name) % 20) * 0.08;
  const rh = isCEO ? 2.5 : 1.2;

  const grp = new THREE.Group();
  const tex = createFacadeTexture(data.color, data.name, w, h, isCEO ? 0.8 : 0.5);
  const body = new THREE.Mesh(new THREE.BoxGeometry(w, h, d),
    new THREE.MeshStandardMaterial({ map: tex, roughness: 0.5, metalness: 0.1 }));
  body.position.y = h/2; body.castShadow = true; body.receiveShadow = true;
  body.userData = { isBuilding: true, buildingName: data.name }; grp.add(body);

  const rc = new THREE.Color(data.color); rc.offsetHSL(0, 0, -0.12);
  const roof = new THREE.Mesh(makeRoof(w*1.1, d*1.1, rh),
    new THREE.MeshStandardMaterial({ color: rc, roughness: 0.7, flatShading: true }));
  roof.position.y = h; roof.castShadow = true;
  roof.userData = { isBuilding: true, buildingName: data.name }; grp.add(roof);

  const baseMat = new THREE.MeshStandardMaterial({ color: 0x2a2a2a, roughness: 0.9 });
  const base = new THREE.Mesh(new THREE.BoxGeometry(w+0.6, 0.15, d+0.6), baseMat);
  base.position.y = 0.075; base.receiveShadow = true; grp.add(base);

  const ringMat = new THREE.MeshStandardMaterial({
    color: STATUS_COLORS[data.status], emissive: STATUS_COLORS[data.status],
    emissiveIntensity: 0.8, transparent: true, opacity: 0.7
  });
  const ring = new THREE.Mesh(new THREE.TorusGeometry(Math.min(w,d)*0.4, 0.08, 12, 24), ringMat);
  ring.rotation.x = Math.PI/2; ring.position.y = 0.1; grp.add(ring);

  const glowMat = new THREE.MeshStandardMaterial({
    color: STATUS_COLORS[data.status], emissive: STATUS_COLORS[data.status],
    emissiveIntensity: 0.3, transparent: true, opacity: 0.25, side: THREE.DoubleSide
  });
  const glow = new THREE.Mesh(new THREE.RingGeometry(Math.min(w,d)*0.44, Math.min(w,d)*0.56, 24), glowMat);
  glow.rotation.x = -Math.PI/2; glow.position.y = 0.05; grp.add(glow);

  const tl = new THREE.Mesh(new THREE.SphereGeometry(0.08, 6, 6),
    new THREE.MeshStandardMaterial({ color: 0xffd54f, emissive: 0xffa000, emissiveIntensity: 0.2 }));
  tl.position.y = h + rh; grp.add(tl);

  const ld = document.createElement('div'); ld.className = 'building-label-3d';
  ld.textContent = data.subject.split(' ').slice(0, 2).join(' ');
  const lbl = new CSS2DObject(ld); lbl.position.set(0, h+rh+1.2, 0); grp.add(lbl);

  const nd = document.createElement('div'); nd.className = 'building-name-3d';
  nd.textContent = data.name;
  const nll = new CSS2DObject(nd); nll.position.set(0, -0.8, 0); grp.add(nll);

  grp.position.set(px, 0, pz);
  grp.userData = { buildingName: data.name, body, roof, ring, glow, labelDiv: ld };
  return grp;
}

function updateBuilding(grp, data) {
  const sc = STATUS_COLORS[data.status] || STATUS_COLORS.idle;
  grp.userData.ring.material.color.setHex(sc); grp.userData.ring.material.emissive.setHex(sc);
  grp.userData.glow.material.color.setHex(sc); grp.userData.glow.material.emissive.setHex(sc);
  grp.userData.labelDiv.textContent = data.subject.split(' ').slice(0, 2).join(' ');
}

// --- Raycasting ---
const raycaster = new THREE.Raycaster(); const pointer = new THREE.Vector2();
function getIntersection(event) {
  const r = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - r.left) / r.width) * 2 - 1;
  pointer.y = -((event.clientY - r.top) / r.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const meshes = [];
  scene.traverse(c => { if (c.isMesh && c.userData.isBuilding) meshes.push(c); });
  const hits = raycaster.intersectObjects(meshes);
  return hits.length ? hits[0].object.userData.buildingName : null;
}

renderer.domElement.addEventListener('click', event => {
  const name = getIntersection(event);
  if (name) selectBuilding(name);
});
renderer.domElement.addEventListener('dblclick', event => {
  const name = getIntersection(event);
  if (name && buildingMap.has(name)) {
    const p = new THREE.Vector3(); buildingMap.get(name).getWorldPosition(p); controls.target.lerp(p, 0.5);
  }
});

// ===================== TAB SYSTEM =====================
let currentBuilding = null;
let buildingData = {};

document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
  });
});

// ===================== CHAT SYSTEM =====================
const chatHistory = {};

function selectBuilding(name) {
  currentBuilding = name;
  chatAgentSelect.value = name;
  if (buildingData[name]) {
    agentTitle.textContent = buildingData[name].subject;
    agentDistrict.textContent = buildingData[name].district;
  } else {
    agentTitle.textContent = name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }
  renderChat(name);
  renderWorkspace(name);
  loadReport(name);
  buildingMap.forEach((g, n) => {
    g.userData.labelDiv.classList.toggle('selected', n === name);
  });
}

const COMMANDS = {
  city_hall: [
    { label: 'Hold Meeting', cmd: 'meeting', desc: 'Run daily standup' },
    { label: 'City Status', cmd: 'city status', desc: 'Overview of all buildings' },
    { label: 'Departments', cmd: 'departments', desc: 'List all agents' },
    { label: 'Last Meeting', cmd: 'last meeting', desc: 'Previous meeting summary' },
  ],
  crypto_trading: [
    { label: 'Buy BTC @ 65k', cmd: 'buy BTC @ 65000', desc: 'Open long' },
    { label: 'Sell ETH @ 3.2k', cmd: 'sell ETH @ 3200', desc: 'Open short' },
    { label: 'Close BTC', cmd: 'close BTC', desc: 'Close position' },
    { label: 'Positions', cmd: 'positions', desc: 'Open positions' },
    { label: 'PnL', cmd: 'pnl', desc: 'Profit & loss' },
    { label: 'Status', cmd: 'status', desc: 'Agent status' },
  ],
  market_data: [
    { label: 'Start Binance', cmd: 'start binance', desc: 'Begin streaming' },
    { label: 'Start Bybit', cmd: 'start bybit', desc: 'Begin streaming' },
    { label: 'Price BTC/USDT', cmd: 'price BTC/USDT', desc: 'Current price' },
    { label: 'Spread BTC/USDT', cmd: 'spread BTC/USDT', desc: 'Bid-ask spread' },
    { label: 'Snapshot', cmd: 'snapshot', desc: 'Full market view' },
    { label: 'Stats', cmd: 'stats', desc: 'Engine stats' },
    { label: 'Pairs', cmd: 'pairs', desc: 'Tracked pairs' },
    { label: 'Stop', cmd: 'stop', desc: 'Stop all streams' },
  ],
  finance_treasury: [
    { label: 'Ledger', cmd: 'ledger', desc: 'Show all entries' },
    { label: 'Summary', cmd: 'summary', desc: 'Totals' },
    { label: 'Add +5000', cmd: 'ledger add trading +5000 capital', desc: 'Credit' },
    { label: 'Add -50', cmd: 'ledger add fees -50 api fees', desc: 'Debit' },
  ],
  finance_building: [
    { label: 'Aggregate', cmd: 'aggregate', desc: 'Combined report' },
    { label: 'Dept Status', cmd: 'dept status crypto_trading', desc: 'Check department' },
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
    { label: 'Queue 15s Kling', cmd: 'queue "prompt" duration 15 kling', desc: 'Generate video' },
  ],
  content_analytics: [
    { label: 'Analyze Strategy', cmd: 'analyze strategy', desc: 'Full analysis' },
    { label: 'Viral Insights', cmd: 'viral insights', desc: 'Trending patterns' },
    { label: 'Trending 10', cmd: 'trending videos 10', desc: 'Hot videos' },
    { label: 'ROI 7 Days', cmd: 'roi analysis 7', desc: 'Return on investment' },
    { label: 'Recommendations', cmd: 'recommendations tech youtube', desc: 'Content ideas' },
    { label: 'Budget Alerts', cmd: 'budget alerts', desc: 'Overspend warnings' },
  ],
  sourcing_research: [
    { label: 'Top Leads', cmd: 'top leads', desc: 'Highest scored' },
    { label: 'New Lead', cmd: 'lead "product" category electronics score 8.5', desc: 'Add opportunity' },
    { label: 'Action Lead', cmd: 'action "product name"', desc: 'Mark actioned' },
    { label: 'Reject Lead', cmd: 'reject "product name"', desc: 'Discard' },
  ],
  research_building: [
    { label: 'Aggregate', cmd: 'aggregate', desc: 'Combined report' },
    { label: 'Dept Status', cmd: 'dept status sourcing_research', desc: 'Check research dept' },
  ],
  media_building: [
    { label: 'Aggregate', cmd: 'aggregate', desc: 'Combined report' },
    { label: 'Dept Status', cmd: 'dept status content_creation', desc: 'Check content dept' },
  ],
};

const WELCOME_INTROS = {
  city_hall: "I'm your CEO. I run daily meetings and track the whole city.",
  crypto_trading: "I trade crypto. Click a command below or type your own.",
  market_data: "I stream live prices from exchanges via WebSocket.",
  finance_treasury: "I track the ledger and aggregate totals.",
  finance_building: "Finance District aggregator. Departments below have their own commands.",
  shopify: "I track store orders, revenue, and profit.",
  product_flipping: "I manage flip inventory — source, list, sell.",
  social_affiliates: "I run affiliate campaigns across platforms.",
  content_creation: "Content pipeline: idea → draft → publish.",
  content_automation: "AI video generation via Kling, Pika, Runway, HeyGen.",
  content_analytics: "Viral intelligence and ROI analysis.",
  sourcing_research: "I score product opportunities.",
  research_building: "Research Quarter aggregator. Select sourcing_research below.",
  media_building: "Media District aggregator. Select departments below.",
};

function renderChat(name) {
  chatMessages.innerHTML = '';
  if (!chatHistory[name] || !chatHistory[name].length) {
    renderWelcome(name);
    return;
  }
  for (const msg of chatHistory[name]) {
    if (typeof msg === 'object' && msg.type === 'buttons') {
      renderButtonRow(msg.commands);
    } else {
      chatMessages.appendChild(createMsgEl(msg.role, msg.text, msg.time));
    }
  }
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function renderWelcome(name) {
  const intro = WELCOME_INTROS[name];
  if (intro) {
    chatMessages.appendChild(createMsgEl('agent', intro, ''));
  }
  const cmds = COMMANDS[name];
  if (cmds && cmds.length) {
    renderButtonRow(cmds);
  }
}

function renderButtonRow(cmds) {
  const row = document.createElement('div');
  row.className = 'cmd-btns';
  const rows = [];
  let cur = [];
  for (const c of cmds) {
    cur.push(c);
    if (cur.length >= 3) { rows.push(cur); cur = []; }
  }
  if (cur.length) rows.push(cur);
  for (const group of rows) {
    const r = document.createElement('div');
    r.className = 'cmd-row';
    for (const c of group) {
      const btn = document.createElement('button');
      btn.className = 'cmd-btn';
      btn.title = c.desc || c.cmd;
      btn.textContent = c.label;
      btn.dataset.cmd = c.cmd;
      btn.addEventListener('click', () => sendCommand(c.cmd));
      r.appendChild(btn);
    }
    row.appendChild(r);
  }
  chatMessages.appendChild(row);
}

function createMsgEl(role, text, time) {
  const el = document.createElement('div');
  el.className = `chat-msg ${role}`;
  const label = role === 'user' ? 'You' : role === 'error' ? 'Error' : currentBuilding || 'Agent';
  el.innerHTML = `<span class="msg-label">${label}</span><div class="msg-text"></div><span class="msg-time">${time || ''}</span>`;
  const textDiv = el.querySelector('.msg-text');
  if (typeof text === 'string' && text.includes('\n')) {
    const pre = document.createElement('pre');
    pre.textContent = text;
    textDiv.appendChild(pre);
  } else {
    textDiv.textContent = typeof text === 'string' ? text : JSON.stringify(text, null, 2);
  }
  return el;
}

async function sendCommand(cmd) {
  const agent = chatAgentSelect.value;
  if (!agent || !cmd) return;
  if (chatInput) chatInput.value = '';
  if (!chatHistory[agent]) chatHistory[agent] = [];
  const now = new Date().toLocaleTimeString();
  chatHistory[agent].push({ role: 'user', text: cmd, time: now });
  if (currentBuilding === agent) {
    const empty = chatMessages.querySelector('.chat-empty');
    if (empty) empty.remove();
    chatMessages.appendChild(createMsgEl('user', cmd, now));
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }
  try {
    const res = await fetch('/api/query', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent, query: cmd }),
    });
    const data = await res.json();
    const rtime = new Date().toLocaleTimeString();
    const ok = data && data.ok;
    const role = ok ? 'agent' : 'error';
    const text = ok ? (data.result || 'ok') : (data && data.error) || 'request failed';
    const displayText = typeof text === 'object' ? JSON.stringify(text, null, 2) : String(text);
    chatHistory[agent].push({ role, text: displayText, time: rtime });
    if (currentBuilding === agent) {
      chatMessages.appendChild(createMsgEl(role, displayText, rtime));
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }
  } catch (e) {
    const etime = new Date().toLocaleTimeString();
    chatHistory[agent].push({ role: 'error', text: e.message, time: etime });
    if (currentBuilding === agent) {
      chatMessages.appendChild(createMsgEl('error', e.message, etime));
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }
  }
}

async function sendChat() {
  const agent = chatAgentSelect.value;
  const query = chatInput ? chatInput.value.trim() : '';
  if (!agent || !query) return;
  if (chatInput) chatInput.value = '';

  if (!chatHistory[agent]) chatHistory[agent] = [];
  const now = new Date().toLocaleTimeString();
  chatHistory[agent].push({ role: 'user', text: query, time: now });

  if (currentBuilding === agent) {
    const empty = chatMessages.querySelector('.chat-empty');
    if (empty) empty.remove();
    chatMessages.appendChild(createMsgEl('user', query, now));
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  try {
    const res = await fetch('/api/query', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent, query }),
    });
    const data = await res.json();
    const rtime = new Date().toLocaleTimeString();
    const role = data.ok ? 'agent' : 'error';
    const text = data.ok ? (data.result || 'ok') : (data.error || 'unknown error');
    chatHistory[agent].push({ role, text: JSON.stringify(text, null, 2), time: rtime });

    if (currentBuilding === agent) {
      chatMessages.appendChild(createMsgEl(role, JSON.stringify(text, null, 2), rtime));
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }
  } catch (e) {
    const etime = new Date().toLocaleTimeString();
    chatHistory[agent].push({ role: 'error', text: e.message, time: etime });
    if (currentBuilding === agent) {
      chatMessages.appendChild(createMsgEl('error', e.message, etime));
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }
  }
}

// chat listeners attached at bottom after DOM guards

// ===================== WORKSPACE SYSTEM =====================
const reportCache = {};

async function renderWorkspace(name) {
  workspaceContent.innerHTML = '<p class="hint" style="padding:20px;">Loading workspace...</p>';
  try {
    const res = await fetch(`/api/agent/${encodeURIComponent(name)}`);
    if (!res.ok) { workspaceContent.innerHTML = '<p class="hint" style="padding:20px;">Failed to load.</p>'; return; }
    const detail = await res.json();
    reportCache[name] = detail;
    const status = (buildingData[name] && buildingData[name].status) || detail.status || 'idle';
    workspaceContent.innerHTML = '';
    const renderer = workspaceRenderers[name] || workspaceRenderers.default;
    renderer(workspaceContent, name, detail, status);
  } catch (e) {
    workspaceContent.innerHTML = `<p class="hint" style="padding:20px;">Error: ${e.message}</p>`;
  }
}

const workspaceRenderers = {};

workspaceRenderers['crypto_trading'] = (el, name, d, status) => {
  const r = d.report || {};
  el.innerHTML = `
    <div class="stat-row">
      <div class="workspace-card"><h3>Status</h3><div class="value ${status === 'working' ? 'yellow' : status === 'error' ? 'red' : 'green'}">${status}</div></div>
      <div class="workspace-card"><h3>Positions</h3><div class="value">${r.open_positions || 0}</div></div>
      <div class="workspace-card"><h3>PnL</h3><div class="value ${(r.pnl||0) >= 0 ? 'green' : 'red'}">$${(r.pnl||0).toFixed(2)}</div></div>
    </div>
    <div class="workspace-card"><h3>Strategy</h3><p class="hint">Total trades: ${r.total_trades||0}. Buy/sell by typing commands in Chat.</p></div>
  `;
};

workspaceRenderers['market_data'] = (el, name, d, status) => {
  const r = d.report || {};
  el.innerHTML = `
    <div class="stat-row">
      <div class="workspace-card"><h3>Running</h3><div class="value ${r.running ? 'green' : 'red'}">${r.running ? 'ON' : 'OFF'}</div></div>
      <div class="workspace-card"><h3>Pairs</h3><div class="value">${r.monitored_pairs || 0}</div></div>
      <div class="workspace-card"><h3>Exchanges</h3><div class="value">${r.active_exchanges || 0}</div></div>
    </div>
    <div class="workspace-card"><h3>Market Data Engine</h3>
      <p class="hint">${r.running ? `Receiving updates. Total: ${r.total_updates||0}` : 'Not started. Try: start binance'}</p>
      <div style="margin-top:6px;font-size:11px;color:#5c6c7a;">
        ${Object.entries(r.updates_per_exchange||{}).map(([ex, n]) => `<div>${ex}: ${n} updates</div>`).join('')}
      </div>
    </div>
  `;
};

workspaceRenderers['finance_treasury'] = (el, name, d, status) => {
  const r = d.report || {};
  el.innerHTML = `
    <div class="stat-row">
      <div class="workspace-card"><h3>Grand Total</h3><div class="value gold">$${(r.grand_total_usd||0).toFixed(2)}</div></div>
      <div class="workspace-card"><h3>Ledger Total</h3><div class="value">$${(r.manual_ledger_total_usd||0).toFixed(2)}</div></div>
    </div>
    <div class="workspace-card"><h3>Manual Ledger</h3>
      <p class="hint">Try: ledger add trading +5000 initial capital</p>
      <p class="hint">Try: ledger</p>
    </div>
  `;
};

workspaceRenderers['finance_building'] = (el, name, d, status) => {
  el.innerHTML = `
    <div class="stat-row">
      <div class="workspace-card"><h3>Status</h3><div class="value ${status === 'working' ? 'yellow' : 'green'}">${status}</div></div>
    </div>
    <div class="workspace-card"><h3>Finance District</h3>
      <p class="hint">crypto_trading — trades BTC/ETH, tracks PnL</p>
      <p class="hint">market_data — live exchange feeds, ticker, spreads</p>
      <p class="hint">finance_treasury — manual ledger, aggregate totals</p>
    </div>
  `;
};

workspaceRenderers['shopify'] = (el, name, d, status) => {
  const r = d.report || {};
  el.innerHTML = `
    <div class="stat-row">
      <div class="workspace-card"><h3>Orders</h3><div class="value">${r.orders||0}</div></div>
      <div class="workspace-card"><h3>Revenue</h3><div class="value green">$${(r.revenue||0).toFixed(2)}</div></div>
      <div class="workspace-card"><h3>Profit</h3><div class="value green">$${(r.profit||0).toFixed(2)}</div></div>
    </div>
    <div class="workspace-card"><h3>Orders</h3>
      <p class="hint">Try: order "t-shirt" revenue 29.99 cost 8.00 dropship</p>
      <p class="hint">Try: revenue, top products</p>
    </div>
  `;
};

workspaceRenderers['product_flipping'] = (el, name, d, status) => {
  const r = d.report || {};
  el.innerHTML = `
    <div class="stat-row">
      <div class="workspace-card"><h3>Inventory</h3><div class="value">${r.open_inventory||0}</div></div>
      <div class="workspace-card"><h3>Sold</h3><div class="value">${r.sold_items||0}</div></div>
      <div class="workspace-card"><h3>Margin</h3><div class="value green">$${(r.total_margin_usd||0).toFixed(2)}</div></div>
    </div>
    <div class="workspace-card"><h3>Flipping Operations</h3>
      <p class="hint">Try: source "item name" cost 25.00 → list "item" target 75.00 → sold "item" for 80.00</p>
      <p class="hint">Try: inventory, margins</p>
    </div>
  `;
};

workspaceRenderers['social_affiliates'] = (el, name, d, status) => {
  const r = d.report || {};
  el.innerHTML = `
    <div class="stat-row">
      <div class="workspace-card"><h3>Campaigns</h3><div class="value">${r.campaigns||0}</div></div>
      <div class="workspace-card"><h3>Revenue</h3><div class="value green">$${(r.revenue||0).toFixed(2)}</div></div>
      <div class="workspace-card"><h3>Conversion</h3><div class="value">${(r.conversion_rate*100||0).toFixed(1)}%</div></div>
    </div>
    <div class="workspace-card"><h3>Affiliate Stats</h3>
      <p><span class="hint">Clicks: ${r.clicks||0} | Conversions: ${r.conversions||0}</span></p>
      <p class="hint">Try: campaign tiktok "my offer"</p>
    </div>
  `;
};

workspaceRenderers['content_creation'] = (el, name, d, status) => {
  const r = d.report || {};
  el.innerHTML = `
    <div class="stat-row">
      <div class="workspace-card"><h3>Ideas</h3><div class="value">${r.ideas||0}</div></div>
      <div class="workspace-card"><h3>Drafts</h3><div class="value yellow">${r.drafts||0}</div></div>
      <div class="workspace-card"><h3>Published</h3><div class="value green">${r.published||0}</div></div>
    </div>
    <div class="workspace-card"><h3>Content Pipeline</h3>
      <p class="hint">Try: idea "my video" for youtube → draft "my video" → publish "my video"</p>
      <p class="hint">Try: queue</p>
    </div>
  `;
};

workspaceRenderers['content_automation'] = (el, name, d, status) => {
  const r = d.report || {};
  const dailyPct = r.daily_budget_remaining_usd != null
    ? Math.max(0, Math.min(100, ((10 - r.daily_budget_remaining_usd) / 10) * 100)) : 0;
  el.innerHTML = `
    <div class="stat-row">
      <div class="workspace-card"><h3>Queue</h3><div class="value">${r.queue_pending||0}</div></div>
      <div class="workspace-card"><h3>Completed</h3><div class="value green">${r.completed_today||0}</div></div>
      <div class="workspace-card"><h3>Failed</h3><div class="value red">${r.failed_today||0}</div></div>
    </div>
    <div class="workspace-card"><h3>Budget</h3>
      <p><span class="hint">Daily remaining: $${(r.daily_budget_remaining_usd||0).toFixed(2)} / Monthly: $${(r.monthly_budget_remaining_usd||0).toFixed(2)}</span></p>
      <div class="budget-bar"><div class="budget-fill ${dailyPct > 80 ? 'crit' : dailyPct > 50 ? 'warn' : 'ok'}" style="width:${dailyPct}%"></div></div>
    </div>
    <div class="workspace-card"><h3>Video Generation</h3>
      <p class="hint">Try: queue "prompt text" duration 15 kling</p>
      <p class="hint">Try: providers, budget, queue status</p>
    </div>
  `;
};

workspaceRenderers['content_analytics'] = (el, name, d, status) => {
  const r = d.report || {};
  el.innerHTML = `
    <div class="stat-row">
      <div class="workspace-card"><h3>ROI</h3><div class="value ${(r.roi_percentage||0) >= 0 ? 'green' : 'red'}">${r.roi_percentage||0}%</div></div>
      <div class="workspace-card"><h3>Videos</h3><div class="value">${r.total_videos||0}</div></div>
      <div class="workspace-card"><h3>Engagement</h3><div class="value yellow">${r.avg_engagement||0}%</div></div>
    </div>
    <div class="workspace-card"><h3>Analytics</h3>
      <p><span class="hint">Top provider: ${r.top_provider||'none'} | Success: ${(r.success_rate*100||0).toFixed(0)}%</span></p>
      <p class="hint">Try: analyze strategy, viral insights, trending videos 10</p>
    </div>
  `;
};

workspaceRenderers['sourcing_research'] = (el, name, d, status) => {
  const r = d.report || {};
  el.innerHTML = `
    <div class="stat-row">
      <div class="workspace-card"><h3>Open Leads</h3><div class="value">${r.open_leads||0}</div></div>
      <div class="workspace-card"><h3>Actioned</h3><div class="value">${r.actioned_leads||0}</div></div>
      <div class="workspace-card"><h3>Avg Score</h3><div class="value gold">${(r.avg_open_score||0).toFixed(1)}</div></div>
    </div>
    <div class="workspace-card"><h3>Research</h3>
      <p class="hint">Try: lead "product" category electronics score 8.5, top leads</p>
      <p class="hint">Try: action "product name", reject "product name"</p>
    </div>
  `;
};

workspaceRenderers['research_building'] = (el, name, d, status) => {
  el.innerHTML = `
    <div class="workspace-card"><h3>Research Quarter</h3>
      <p class="hint">sourcing_research — scores product opportunities</p>
    </div>
  `;
};

workspaceRenderers['media_building'] = (el, name, d, status) => {
  el.innerHTML = `
    <div class="workspace-card"><h3>Media District</h3>
      <p class="hint">content_creation — idea → draft → publish pipeline</p>
      <p class="hint">content_automation — AI video generation (Kling, Pika, Runway, HeyGen)</p>
      <p class="hint">content_analytics — viral intelligence, ROI analysis</p>
    </div>
  `;
};

workspaceRenderers['city_hall'] = (el, name, d, status) => {
  const r = d.report || {};
  el.innerHTML = `
    <div class="stat-row">
      <div class="workspace-card"><h3>Meetings Held</h3><div class="value">${r.meetings_held||0}</div></div>
      <div class="workspace-card"><h3>Buildings</h3><div class="value">${Object.keys(buildingData).length}</div></div>
    </div>
    <div class="workspace-card"><h3>City Overview</h3>
      <p class="hint">Click "Hold Meeting" below for a full report.</p>
      <div style="margin-top:6px;">
        ${Object.entries(buildingData).map(([n, b]) =>
          `<div class="inv-item"><span>${b.subject}</span><span class="badge ${b.status === 'idle' ? 'badge-green' : b.status === 'working' ? 'badge-yellow' : 'badge-red'}">${b.status}</span></div>`
        ).join('')}
      </div>
    </div>
  `;
};

workspaceRenderers['default'] = (el, name, d, status) => {
  const r = d.report || {};
  const fields = Object.entries(r);
  el.innerHTML = `
    <div class="stat-row">
      <div class="workspace-card"><h3>Status</h3><div class="value ${status === 'working' ? 'yellow' : status === 'error' ? 'red' : 'green'}">${status}</div></div>
      <div class="workspace-card"><h3>District</h3><div class="value" style="font-size:14px;">${d.district}</div></div>
    </div>
    <div class="workspace-card"><h3>Report Data</h3>
      ${fields.length ? fields.map(([k, v]) =>
        `<div class="inv-item"><span>${k}</span><span>${typeof v === 'object' ? JSON.stringify(v) : v}</span></div>`
      ).join('') : '<p class="hint">No report data.</p>'}
    </div>
  `;
};

// ===================== REPORT TAB =====================
async function loadReport(name) {
  if (!reportContent || !reportEvents) return;
  try {
    const res = await fetch(`/api/agent/${encodeURIComponent(name)}`);
    if (!res.ok) {
      reportContent.innerHTML = '<p class="hint">Failed to load report.</p>';
      reportEvents.innerHTML = '';
      return;
    }
    const data = await res.json();
    const reportRows = Object.entries(data.report || {})
      .filter(([k]) => k !== 'agent' && k !== 'subject')
      .map(([k, v]) => `<tr><td>${k}</td><td>${typeof v === 'object' ? JSON.stringify(v) : v}</td></tr>`)
      .join('');
    reportContent.innerHTML = reportRows
      ? `<table class="report-grid">${reportRows}</table>`
      : '<p class="hint">No report data.</p>';
    const events = (data.recent_events || [])
      .map((e) => `<div class="event-item"><span class="ts">${e.timestamp || ''}</span> — ${e.type || ''}: ${e.message || ''}</div>`)
      .join('');
    reportEvents.innerHTML = events || '<p class="hint">No activity yet.</p>';
  } catch (err) {
    reportContent.innerHTML = `<p class="hint">Error: ${err.message}</p>`;
    reportEvents.innerHTML = '';
  }
}

// ===================== CITY STREAM / BUILDINGS =====================
let agentSelectPopulated = false;

function updateCity(buildings) {
  if (!Array.isArray(buildings)) return;
  buildingData = {};
  for (const b of buildings) {
    buildingData[b.name] = b;
    if (buildingMap.has(b.name)) {
      updateBuilding(buildingMap.get(b.name), b);
    } else {
      const grp = createBuilding(b);
      buildingMap.set(b.name, grp);
      scene.add(grp);
    }
  }
  // remove buildings no longer present
  for (const name of [...buildingMap.keys()]) {
    if (!buildingData[name]) {
      const grp = buildingMap.get(name);
      scene.remove(grp);
      buildingMap.delete(name);
    }
  }
  if (!agentSelectPopulated && buildings.length && chatAgentSelect) {
    chatAgentSelect.innerHTML = buildings
      .map((b) => `<option value="${b.name}">${b.subject || b.name}</option>`)
      .join('');
    agentSelectPopulated = true;
  }
  if (loadingScreen && !loadingScreen.classList.contains('done')) {
    loadingScreen.classList.add('done');
  }
}

function connectStream() {
  if (!indicator) return;
  const es = new EventSource('/api/stream');
  es.onopen = () => {
    indicator.textContent = 'live';
    indicator.className = 'connected';
  };
  es.onerror = () => {
    indicator.textContent = 'reconnecting…';
    indicator.className = 'disconnected';
  };
  es.onmessage = (evt) => {
    try {
      updateCity(JSON.parse(evt.data));
    } catch (e) {
      console.error('bad city state payload', e);
    }
  };
  // fallback if SSE stalled
  fetch('/api/city')
    .then((r) => r.json())
    .then(updateCity)
    .catch((e) => {
      console.error('initial /api/city failed', e);
      if (loadingScreen) {
        loadingScreen.textContent = 'Failed to load city state — check server';
      }
    });
}

// ===================== MEETING =====================
const meetingBtn = document.getElementById('trigger-meeting');
if (meetingBtn && meetingOutput) {
  meetingBtn.addEventListener('click', async () => {
    meetingOutput.textContent = 'holding meeting…';
    try {
      const res = await fetch('/api/meeting', { method: 'POST' });
      const data = await res.json();
      meetingOutput.textContent = JSON.stringify(data, null, 2);
    } catch (e) {
      meetingOutput.textContent = e.message;
    }
  });
}

// ===================== RESIZE =====================
function resize() {
  if (!container) return;
  const w = container.clientWidth || 1;
  const h = container.clientHeight || 1;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
  composer.setSize(w, h);
  labelRenderer.setSize(w, h);
}
window.addEventListener('resize', resize);

// ===================== ANIMATION =====================
function animate() {
  requestAnimationFrame(animate);
  controls.update();
  const t = Date.now() * 0.001;
  buildingMap.forEach((g) => {
    const r = g.userData.glow;
    if (r) {
      const s = 1 + 0.06 * Math.sin(t * 2);
      r.scale.set(s, s, 1);
      r.material.opacity = 0.15 + 0.1 * Math.sin(t * 2);
    }
  });
  composer.render();
  labelRenderer.render(scene, camera);
}

// Guard chat controls if HTML missing (should exist after template fix)
if (chatSend && chatInput) {
  chatSend.addEventListener('click', sendChat);
  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendChat();
  });
}

connectStream();
animate();
resize();
