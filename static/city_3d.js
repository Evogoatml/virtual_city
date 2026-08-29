import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';

const container = document.getElementById('canvas-container');
const loadingScreen = document.getElementById('loading-screen');
const indicator = document.getElementById('connection-indicator');

// Inspector (single contextual panel)
const inspector = document.getElementById('inspector');
const inspTitle = document.getElementById('insp-title');
const inspDistrict = document.getElementById('insp-district');
const inspStatus = document.getElementById('insp-status');
const inspAutonomy = document.getElementById('insp-autonomy');
const inspKpis = document.getElementById('insp-kpis');
const inspDash = document.getElementById('insp-dash');
const inspEvents = document.getElementById('insp-events');
const inspTraces = document.getElementById('insp-traces');
const inspCmds = document.getElementById('insp-cmds');
const chatLog = document.getElementById('chat-log');
const chatInput = document.getElementById('chat-input');
const chatSend = document.getElementById('chat-send');

// City HUD
const hudTreasury = document.getElementById('hud-treasury');
const hudWorking = document.getElementById('hud-working');
const hudIdle = document.getElementById('hud-idle');
const hudError = document.getElementById('hud-error');
const hudEsc = document.getElementById('hud-esc');

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
const STATUS_COLORS = { idle: 0x4caf50, working: 0xffb300, error: 0xe53935, paused: 0x607d8b };
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
  const ringStatus = data.paused ? 'paused' : data.status;

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
    color: STATUS_COLORS[ringStatus] || STATUS_COLORS.idle, emissive: STATUS_COLORS[ringStatus] || STATUS_COLORS.idle,
    emissiveIntensity: 0.8, transparent: true, opacity: 0.7
  });
  const ring = new THREE.Mesh(new THREE.TorusGeometry(Math.min(w,d)*0.4, 0.08, 12, 24), ringMat);
  ring.rotation.x = Math.PI/2; ring.position.y = 0.1; grp.add(ring);

  const glowMat = new THREE.MeshStandardMaterial({
    color: STATUS_COLORS[ringStatus] || STATUS_COLORS.idle, emissive: STATUS_COLORS[ringStatus] || STATUS_COLORS.idle
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
  const status = data.paused ? 'paused' : data.status;
  const sc = STATUS_COLORS[status] || STATUS_COLORS.idle;
  grp.userData.ring.material.color.setHex(sc); grp.userData.ring.material.emissive.setHex(sc);
  grp.userData.glow.material.color.setHex(sc); grp.userData.glow.material.emissive.setHex(sc);
  grp.userData.labelDiv.textContent = data.subject.split(' ').slice(0, 2).join(' ');
}

// ===================== DISTRICT + STREET LABELS =====================
// Map pixel grid (city_grid) -> world space, matching createBuilding.
function gridToWorld(gx, gy) {
  const sc = 0.05, cx = 400, cy = 240;
  return { x: (gx - cx) * sc, z: (gy - cy) * sc };
}

const districtGroup = new THREE.Group();
scene.add(districtGroup);
const DISTRICT_LABEL_COLORS = {
  Financial: '#ffcc80',
  Media:     '#ce93d8',
  Research:  '#80cbc4',
  Commerce:  '#c5e1a5',
};

function renderOverlay(state) {
  if (!state) return;
  for (let i = districtGroup.children.length - 1; i >= 0; i--) {
    districtGroup.remove(districtGroup.children[i]);
  }

  // District plaques
  const districts = state.districts || {};
  for (const [dname, meta] of Object.entries(districts)) {
    const [gx, gy] = Array.isArray(meta.center) ? meta.center : [0, 0];
    const p = gridToWorld(gx, gy);
    const div = document.createElement('div');
    div.className = 'district-patch';
    div.textContent = dname;
    div.style.color = DISTRICT_LABEL_COLORS[dname] || '#9fb3c9';
    const obj = new CSS2DObject(div);
    obj.position.set(p.x, 0.15, p.z);
    districtGroup.add(obj);
  }

  // Street signs
  const streets = state.streets || [];
  for (const s of streets) {
    const div = document.createElement('div');
    div.className = 'street-sign';
    div.textContent = s.name;
    const obj = new CSS2DObject(div);
    if (s.axis === 'vertical') {
      // vertical street runs N-S at city-grid x; sign at mid depth (town center row)
      obj.position.set(gridToWorld(s.at, 0).x, 0.12, 0.05);
    } else {
      // horizontal street runs E-W at grid y; sign at mid width
      obj.position.set(0.05, 0.12, gridToWorld(0, s.at).z);
    }
    districtGroup.add(obj);
  }
}

function loadOverlay() {
  fetch('/api/city')
    .then((r) => r.json())
    .then(renderOverlay)
    .catch(() => {});
}
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
  else closeInspector();
});
renderer.domElement.addEventListener('dblclick', event => {
  const name = getIntersection(event);
  if (name && buildingMap.has(name)) {
    enterBuilding(name);
  }
});

// ===================== INSPECTOR (single contextual panel) =====================
let currentBuilding = null;
let buildingData = {};
const chatHistory = {};

// ===================== ENTER BUILDING (3D Metaverse Interior) =====================
let interiorScene = null;
let exteriorBuildings = [];
let cameraTarget = null;

function enterBuilding(name) {
  if (!buildingMap.has(name)) return;
  const grp = buildingMap.get(name);
  const p = new THREE.Vector3();
  grp.getWorldPosition(p);

  // Despawn all buildings
  exteriorBuildings = [];
  for (const [n, g] of buildingMap) {
    exteriorBuildings.push({ name: n, group: g });
    scene.remove(g);
  }

  // Spawn interior room
  const room = createInteriorRoom(name, grp);
  interiorScene = room;
  scene.add(room);

  // Fly camera inside
  cameraTarget = name;
  const camPos = new THREE.Vector3(p.x, p.y + 2, p.z + 4);
  const fly = new TWEEN.Tween(camera.position).to(
    { x: p.x, y: p.y + 2.5, z: p.z + 5 }, 1200
  ).easing(TWEEN.Easing.Cubic.InOut);
  fly.start();

  controls.target.set(p.x, p.y + 2, p.z);
  controls.update();

  // Show exit prompt
  const exitBtn = document.getElementById('exit-building');
  if (exitBtn) exitBtn.style.display = 'block';

  // Load interior dashboard
  fetch('/api/building/' + encodeURIComponent(name) + '/dashboard')
    .then(r => r.json())
    .then(data => {
      const display = document.getElementById('interior-display');
      if (display && typeof dash === 'function') {
        display.innerHTML = dash(name, data);
        display.style.display = 'block';
      }
    })
    .catch(() => {});

  document.getElementById('enter-building').style.display = 'none';
}

function exitBuilding() {
  // Remove interior
  if (interiorScene) {
    scene.remove(interiorScene);
    interiorScene = null;
  }

  const display = document.getElementById('interior-display');
  if (display) display.style.display = 'none';

  const exitBtn = document.getElementById('exit-building');
  if (exitBtn) exitBtn.style.display = 'none';

  // Restore buildings
  for (const { name, group } of exteriorBuildings) {
    scene.add(group);
  }
  exteriorBuildings = [];

  // Zoom camera back out to overview
  const camPos = new TWEEN.Tween(camera.position).to(
    { x: 28, y: 22, z: 28 }, 1500
  ).easing(TWEEN.Easing.Cubic.InOut);
  camPos.start();
  controls.target.set(0, 3, 0);
  controls.update();

  cameraTarget = null;
}

function togglePause() {
  if (!currentBuilding) return;
  const isPaused = buildingData[currentBuilding]?.paused || false;
  const action = isPaused ? 'resume' : 'pause';
  fetch('/api/agent/' + encodeURIComponent(currentBuilding) + '/' + action)
    .then(r => r.json())
    .then(data => {
      const btn = document.getElementById('pause-building');
      if (btn) btn.textContent = data.paused ? 'Resume' : 'Pause';
      buildingData[currentBuilding] = buildingData[currentBuilding] || {};
      buildingData[currentBuilding].paused = data.paused;
    })
    .catch(() => {});
}

function createInteriorRoom(name, buildingGroup) {
  const grp = new THREE.Group();
  const p = new THREE.Vector3();
  buildingGroup.getWorldPosition(p);

  // Room walls (floor + 4 walls + ceiling)
  const wallMat = new THREE.MeshStandardMaterial({
    color: 0x0a1420, roughness: 0.7, transparent: true, opacity: 0.85
  });
  const floorMat = new THREE.MeshStandardMaterial({ color: 0x0d1a2a, roughness: 0.85 });

  const w = 6, d = 6, h = 3.5;
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(w, d), floorMat);
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = 0.01;
  floor.receiveShadow = true;
  grp.add(floor);

  const wallGeo = new THREE.PlaneGeometry(w, h);
  const walls = [
    { rot: [0, 0, 0], pos: [0, h/2, -d/2] },       // back
    { rot: [0, Math.PI, 0], pos: [0, h/2, d/2] },   // front
    { rot: [0, -Math.PI/2, 0], pos: [-w/2, h/2, 0] }, // left
    { rot: [0, Math.PI/2, 0], pos: [w/2, h/2, 0] },   // right
  ];
  for (const wConf of walls) {
    const wm = new THREE.Mesh(wallGeo, wallMat);
    wm.rotation.set(...wConf.rot);
    wm.position.set(...wConf.pos);
    wm.receiveShadow = true;
    grp.add(wm);
  }

  // Ceiling grid
  const ceilMat = new THREE.MeshStandardMaterial({ color: 0x1a2a3a, roughness: 0.9 });
  const ceil = new THREE.Mesh(new THREE.PlaneGeometry(w, d), ceilMat);
  ceil.rotation.x = Math.PI / 2;
  ceil.position.y = h - 0.01;
  ceil.receiveShadow = true;
  grp.add(ceil);

  // Holographic display panels (front wall)
  const panelGeo = new THREE.PlaneGeometry(3, 1.5);
  const panelMat = new THREE.MeshBasicMaterial({
    color: 0x00d4ff, transparent: true, opacity: 0.15, side: THREE.DoubleSide
  });
  for (let i = 0; i < 2; i++) {
    const panel = new THREE.Mesh(panelGeo, panelMat);
    panel.position.set(i === 0 ? -1 : 1, h * 0.6, -d/2 + 0.05);
    panel.rotation.y = Math.PI;
    grp.add(panel);
  }

  // Data pedestal (center)
  const pedestalGeo = new THREE.CylinderGeometry(0.8, 1, 0.3, 16);
  const pedestalMat = new THREE.MeshStandardMaterial({ color: 0x1a3a5a, roughness: 0.5 });
  const pedestal = new THREE.Mesh(pedestalGeo, pedestalMat);
  pedestal.position.y = 0.15;
  pedestal.receiveShadow = true;
  pedestal.castShadow = true;
  grp.add(pedestal);

  const glowMat = new THREE.MeshBasicMaterial({
    color: 0x00d4ff, transparent: true, opacity: 0.4, side: THREE.DoubleSide
  });
  const glow = new THREE.Mesh(
    new THREE.RingGeometry(0.7, 0.95, 32), glowMat
  );
  glow.rotation.x = -Math.PI / 2;
  glow.position.y = 0.31;
  grp.add(glow);

  // Label
  const ld = document.createElement('div');
  ld.className = 'building-label-3d';
  ld.textContent = name.replace(/_/g, ' ');
  const lbl = new CSS2DObject(ld);
  lbl.position.set(0, h, 0);
  grp.add(lbl);

  grp.position.set(p.x, p.y, p.z);
  return grp;
}

// ===================== RENDER =====================

function statusPillClass(status) {
  return status === 'paused' ? 'paused' :
         status === 'working' ? 'working' :
         status === 'error' ? 'error' : 'idle';
}

function loadBuildingState(name) {
  fetch('/api/agent/' + encodeURIComponent(name))
    .then(r => r.json())
    .then(d => {
      buildingData[name] = buildingData[name] || {};
      buildingData[name].status = d.status || buildingData[name].status;
      buildingData[name].paused = d.paused !== undefined ? d.paused : buildingData[name].paused;
    })
    .catch(() => {});
}

function closeInspector() {
  currentBuilding = null;
  if (inspector) inspector.classList.remove('open');
  buildingMap.forEach((g) => {
    g.userData.labelDiv.classList.remove('selected');
  });
}

function selectBuilding(name) {
  currentBuilding = name;
  const meta = buildingData[name] || {};
  inspTitle.textContent = meta.subject
    || name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  inspDistrict.textContent = meta.district || '';
  const st = meta.paused ? 'paused' : (meta.status || 'idle');
  inspStatus.textContent = st;
  inspStatus.className = 'pill ' + statusPillClass(st);
  inspAutonomy.textContent = meta.autonomy || '…';
  chatLog.innerHTML = '';
  renderWelcome(name);
  renderCommands(name);
  inspector.classList.add('open');
  loadInspector(name);
  buildingMap.forEach((g, n) => {
    g.userData.labelDiv.classList.toggle('selected', n === name);
  });
  document.getElementById('enter-building').style.display = 'block';

  const pauseBtn = document.getElementById('pause-building');
  if (pauseBtn) {
    const isPaused = buildingData[name]?.paused;
    pauseBtn.textContent = isPaused ? 'Resume' : 'Pause';
    pauseBtn.onclick = togglePause;
  }
}

async function loadInspector(name) {
  inspDash.innerHTML = '<p class="hint">Loading dashboard…</p>';
  inspEvents.innerHTML = '<p class="hint">…</p>';
  inspTraces.innerHTML = '<p class="hint">…</p>';
  try {
    const res = await fetch('/api/building/' + encodeURIComponent(name) + '/dashboard');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    inspDash.innerHTML = (typeof dash === 'function')
      ? dash(name, data)
      : '<pre class="dash-json">' + escapeHtml(JSON.stringify(data, null, 2)) + '</pre>';
    inspKpis.innerHTML = kpiCards(data.report || {});
    const events = data.events || [];
    inspEvents.innerHTML = events.length
      ? events.map((e) =>
          '<div class="monitor-event"><span class="ts">' + escapeHtml((e.timestamp || '').slice(0, 16))
          + '</span> <span class="type">' + escapeHtml(e.type || '') + '</span> — '
          + escapeHtml(e.message || '') + '</div>').join('')
      : '<p class="hint">No activity yet.</p>';
    document.querySelector('#insp-activity summary').textContent =
      'Activity' + (events.length ? ' (' + events.length + ')' : '');
    const traces = data.traces || [];
    inspTraces.innerHTML = (typeof renderTraceHtml === 'function' && traces.length)
      ? renderTraceHtml(traces)
      : '<p class="hint">No reasoning activity yet.</p>';
    document.querySelector('#insp-reasoning summary').textContent =
      'Reasoning trace' + (traces.length ? ' (' + traces.length + ')' : '');
  } catch (err) {
    inspDash.innerHTML = '<p class="hint">Dashboard failed to load: ' + escapeHtml(err.message) + '</p>';
  }
  try {
    const res = await fetch('/api/agent/' + encodeURIComponent(name));
    if (res.ok) {
      const d = await res.json();
      if (d.autonomy) {
        inspAutonomy.textContent = d.autonomy;
        buildingData[name] = Object.assign({}, buildingData[name] || {}, { autonomy: d.autonomy });
      }
    }
  } catch (e) { /* non-critical */ }
}

// ===================== KPI CARDS =====================
const KPI_LABELS = {
  revenue_usd: ['Revenue', (v) => '$' + fmtNum(v)],
  total_revenue_usd: ['Revenue', (v) => '$' + fmtNum(v)],
  profit_usd: ['Profit', (v) => '$' + fmtNum(v)],
  treasury_usd: ['Treasury', (v) => '$' + fmtNum(v)],
  balance_btc: ['Balance', (v) => fmtBtc(v)],
  total_published: ['Published', (v) => String(v)],
  total_videos: ['Videos', (v) => String(v)],
  total_ideas: ['Ideas', (v) => String(v)],
  open_positions: ['Positions', (v) => String(v)],
  open_leads: ['Open leads', (v) => String(v)],
  meetings_held: ['Meetings', (v) => String(v)],
  campaigns: ['Campaigns', (v) => String(v)],
  scans_total: ['Scans', (v) => String(v)],
  roi_percentage: ['ROI', (v) => v + '%'],
  pending_approvals: ['Approvals', (v) => String(v)],
};

function kpiCards(report) {
  const out = [];
  const seen = new Set();
  for (const [key, [label, fmt]] of Object.entries(KPI_LABELS)) {
    if (out.length >= 4) break;
    const v = report[key];
    if (v === undefined || v === null || seen.has(key)) continue;
    seen.add(key);
    out.push('<div class="kpi"><div class="k">' + label + '</div><div class="v">' + fmt(v) + '</div></div>');
  }
  for (const [k, v] of Object.entries(report)) {
    if (out.length >= 4) break;
    if (typeof v !== 'number' || seen.has(k)) continue;
    if (['agent', 'subject'].includes(k)) continue;
    seen.add(k);
    const label = k.replace(/_/g, ' ').slice(0, 12);
    out.push('<div class="kpi"><div class="k">' + escapeHtml(label) + '</div><div class="v">'
      + (Number.isInteger(v) ? v : v.toFixed(2)) + '</div></div>');
  }
  return out.join('');
}

// ===================== CITY HUD =====================
function updateHudCounts(buildings) {
  if (!Array.isArray(buildings)) return;
  let w = 0, i = 0, e = 0;
  for (const b of buildings) {
    if (b.status === 'working') w++;
    else if (b.status === 'error') e++;
    else i++;
  }
  if (hudWorking) hudWorking.textContent = w;
  if (hudIdle) hudIdle.textContent = i;
  if (hudError) hudError.textContent = e;
}

function updateHudMoney(mgr) {
  if (!mgr) return;
  if (hudTreasury && typeof mgr.treasury === 'number') {
    hudTreasury.textContent = '$' + fmtNum(mgr.treasury);
  }
  if (hudEsc && typeof mgr.open_escalations === 'number') {
    hudEsc.textContent = mgr.open_escalations;
  }
}

function pollManager() {
  fetch('/api/manager')
    .then((r) => r.json())
    .then(updateHudMoney)
    .catch(() => {});
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
    { label: 'Aggregate', cmd: 'aggregate', desc: 'Combined content report' },
    { label: 'Queue', cmd: 'queue', desc: 'Ideas in pipeline' },
    { label: 'New Idea', cmd: 'idea sunset painting for tiktok', desc: 'Add idea' },
    { label: 'Video Queue', cmd: 'video queue', desc: 'AI video jobs' },
    { label: 'Viral Insights', cmd: 'viral insights', desc: 'Analytics' },
    { label: 'Recommend', cmd: 'recommend lifestyle instagram', desc: 'Content ideas' },
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
  media_building: "Media Building — creation, AI automation, and analytics in one place.",
};

// ----- Inspector chat (contextual: bound to the selected building) -----
function renderWelcome(name) {
  const intro = WELCOME_INTROS[name];
  if (intro) chatLog.appendChild(createMsgEl('agent', intro, ''));
}

function renderCommands(name) {
  inspCmds.innerHTML = '';
  const cmds = COMMANDS[name] || [];
  for (const c of cmds) {
    const btn = document.createElement('button');
    btn.className = 'cmd-btn';
    btn.title = c.desc || c.cmd;
    btn.textContent = c.label;
    btn.addEventListener('click', () => sendCommand(c.cmd));
    inspCmds.appendChild(btn);
  }
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

function scrollChat() {
  chatLog.scrollTop = chatLog.scrollHeight;
}

async function sendCommand(cmd) {
  const agent = currentBuilding;
  if (!agent || !cmd) return;
  const now = new Date().toLocaleTimeString();
  chatLog.appendChild(createMsgEl('user', cmd, now));
  const typing = document.createElement('div');
  typing.className = 'typing';
  typing.textContent = '…working';
  chatLog.appendChild(typing);
  scrollChat();
  try {
    const res = await fetch('/api/query', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent, query: cmd }),
    });
    const data = await res.json();
    typing.remove();
    const role = data && data.ok ? 'agent' : 'error';
    const text = data && data.ok ? (data.result || 'ok') : (data && data.error) || 'request failed';
    const displayText = typeof text === 'object' ? JSON.stringify(text, null, 2) : String(text);
    chatLog.appendChild(createMsgEl(role, displayText, new Date().toLocaleTimeString()));
    scrollChat();
    // refresh the dashboard if the command may have changed data
    if (data && data.ok) loadInspector(agent);
  } catch (e) {
    typing.remove();
    chatLog.appendChild(createMsgEl('error', e.message, new Date().toLocaleTimeString()));
    scrollChat();
  }
}

async function sendChat() {
  const query = chatInput ? chatInput.value.trim() : '';
  if (!currentBuilding || !query) return;
  chatInput.value = '';
  sendCommand(query);
}
// ===================== CITY STREAM / BUILDINGS =====================
let agentSelectPopulated = false;

function updateCity(data) {
  const buildings = Array.isArray(data) ? data : (data.buildings || []);
  if (!buildings || !buildings.length) return;
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
  updateHudCounts(buildings);
  // live-refresh the selected building's status pill
  if (currentBuilding && inspStatus && buildingData[currentBuilding]) {
    const st = buildingData[currentBuilding].status || 'idle';
    inspStatus.textContent = st;
    inspStatus.className = 'pill ' + statusPillClass(st);
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
    .then((state) => {
      updateCity(Array.isArray(state) ? state : (state.buildings || []));
      loadOverlay();
    })
    .then(() => fetch('/api/agents').then(r => r.json()).then(agents => {
      for (const a of agents) {
        if (buildingData[a.name]) buildingData[a.name].paused = a.paused;
      }
      const btn = document.getElementById('pause-building');
      if (btn && currentBuilding && buildingData[currentBuilding]) {
        btn.textContent = buildingData[currentBuilding].paused ? 'Resume' : 'Pause';
      }
    }).catch(() => {}))
    .catch((e) => {
      console.error('initial /api/city failed', e);
      if (loadingScreen) {
        loadingScreen.textContent = 'Failed to load city state — check server';
      }
    });
}

// ===================== MEETING =====================
const meetingBtn = document.getElementById('trigger-meeting');
if (meetingBtn) {
  meetingBtn.addEventListener('click', async () => {
    meetingBtn.textContent = 'Meeting…';
    try {
      await fetch('/api/meeting', { method: 'POST' });
    } catch (e) { /* non-critical */ }
    meetingBtn.textContent = 'Hold Meeting';
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
  TWEEN.update();
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

// Guard chat controls if HTML missing
if (chatSend && chatInput) {
  chatSend.addEventListener('click', sendChat);
  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendChat();
  });
}

// Inspector close controls
const inspCloseBtn = document.getElementById('insp-close');
if (inspCloseBtn) inspCloseBtn.addEventListener('click', closeInspector);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && cameraTarget) {
    exitBuilding();
  } else if (e.key === 'Escape') {
    closeInspector();
  }
});

connectStream();
pollManager();
setInterval(pollManager, 20000);
animate();
resize();
