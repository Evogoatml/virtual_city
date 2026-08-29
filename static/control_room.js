/**
 * control_room.js — 3D interior command center for controll_panel.
 *
 * When the user clicks the controll_panel building and opens the "Interior"
 * tab, this renders a WebGL scene of a massive computer command center:
 * console banks, avatar stations for each building, and a central holotable
 * showing the pipeline routes.
 *
 * Visual style matches the dark-mode SaaS analytics dashboard:
 * deep charcoal background, purple/violet accents, blue secondary,
 * green for idle/active, red/orange for errors.
 */
(function () {
  'use strict';

  var canvasEl = null;
  var THREE = window.THREE;
  var scene, camera, renderer, controls, labelRenderer;
  var buildingAvatars = {};
  var animationId = null;
  var isInitialized = false;
  var resizeHandler = null;

  // Palette matching the dashboard image
  var PALETTE = {
    bg: 0x070b12,       // deep charcoal
    panel: 0x0d1421,     // slightly lighter for panels
    accent_purple: 0x7c5cfc,  // primary accent (purple)
    accent_blue: 0x22d3ee,    // secondary (blue)
    idle: 0x4caf50,     // green
    working: 0xffb300,  // gold/orange
    error: 0xe53935,    // red
    text: 0x8899cc,
  };

  function ensureCanvas() {
    if (canvasEl) return canvasEl;
    canvasEl = document.getElementById('control-room-canvas');
    if (canvasEl) {
      canvasEl.style.width = '100%';
      canvasEl.style.height = '100%';
      canvasEl.style.display = 'block';
    }
    return canvasEl;
  }

  function hashColor(str) {
    var h = 0;
    for (var i = 0; i < str.length; i++) h = ((h << 5) - h) + str.charCodeAt(i) | 0;
    h = Math.abs(h);
    // Use the purple accent for most, with hue variation
    var hue = (h % 360) / 360;
    return new THREE.Color().setHSL(hue * 0.15 + 0.65, 0.7, 0.55);
  }

  function createAvatarStation(name, color, index, total) {
    var group = new THREE.Group();

    // Desk / console base — dark panel style
    var deskGeo = new THREE.BoxGeometry(1.8, 0.1, 0.7);
    var deskMat = new THREE.MeshStandardMaterial({
      color: PALETTE.panel, roughness: 0.7, metalness: 0.3
    });
    var desk = new THREE.Mesh(deskGeo, deskMat);
    desk.position.y = 0.05;
    desk.castShadow = true; desk.receiveShadow = true;
    group.add(desk);

    // Holographic screen — purple accent
    var screenGeo = new THREE.PlaneGeometry(1.4, 0.5);
    var screenMat = new THREE.MeshStandardMaterial({
      color: PALETTE.accent_purple, emissive: PALETTE.accent_purple,
      emissiveIntensity: 0.25, transparent: true, opacity: 0.7,
      side: THREE.DoubleSide
    });
    var screen = new THREE.Mesh(screenGeo, screenMat);
    screen.position.y = 0.2;
    screen.position.z = 0.4;
    screen.rotation.x = -0.1;
    group.add(screen);

    // Avatar figure (simple stick-figure with colored badge)
    var avatarMat = new THREE.MeshStandardMaterial({ color: 0xbbbbbb });
    var headGeo = new THREE.SphereGeometry(0.12, 8, 8);
    var head = new THREE.Mesh(headGeo, avatarMat);
    head.position.y = 0.65;
    head.castShadow = true;
    group.add(head);

    var bodyGeo;
    if (THREE.CapsuleGeometry) {
      bodyGeo = new THREE.CapsuleGeometry(0.08, 0.4, 4, 8);
    } else {
      bodyGeo = new THREE.BoxGeometry(0.16, 0.4, 0.1);
    }
    var body = new THREE.Mesh(bodyGeo, avatarMat);
    body.position.y = 0.4;
    body.castShadow = true;
    group.add(body);

    // Status indicator light on the desk
    var indicatorGeo = new THREE.SphereGeometry(0.03, 8, 8);
    var indicatorMat = new THREE.MeshStandardMaterial({
      color: PALETTE.idle, emissive: PALETTE.idle,
      emissiveIntensity: 0.5, transparent: true, opacity: 0.8
    });
    var indicator = new THREE.Mesh(indicatorGeo, indicatorMat);
    indicator.position.y = 0.15;
    indicator.position.x = 0.6;
    indicator.userData = { isStatusLight: true };
    group.add(indicator);

    // Building name label
    var labelDiv = document.createElement('div');
    labelDiv.className = 'avatar-label';
    labelDiv.textContent = name;
    var labelObj = new THREE.CSS2DObject(labelDiv);
    labelObj.position.set(0, 0.8, 0);
    group.add(labelObj);

    // Position around an arc facing inward
    var angle = -Math.PI / 2 + (index / Math.max(total - 1, 1)) * Math.PI;
    var radius = 4.5;
    var r = radius + Math.random() * 0.3;
    group.position.x = Math.cos(angle) * r;
    group.position.z = Math.sin(angle) * r;
    group.rotation.y = -angle - Math.PI / 2;
    group.userData = { name: name, status: 'idle', screenMat: screenMat, indicatorMat: indicatorMat };

    return group;
  }

  function createHolotable(buildings) {
    var group = new THREE.Group();
    group.userData = { routes: [] };

    // Central table surface — translucent purple
    var geo = new THREE.CylinderGeometry(2.5, 2.5, 0.1, 32);
    var mat = new THREE.MeshStandardMaterial({
      color: PALETTE.accent_purple, emissive: PALETTE.accent_purple,
      emissiveIntensity: 0.1, transparent: true, opacity: 0.25,
      side: THREE.DoubleSide
    });
    var table = new THREE.Mesh(geo, mat);
    table.position.y = 2.2;
    group.add(table);

    // Glowing center column
    var colGeo = new THREE.CylinderGeometry(0.08, 0.08, 1.5, 16);
    var colMat = new THREE.MeshStandardMaterial({
      color: PALETTE.accent_blue, emissive: PALETTE.accent_blue,
      emissiveIntensity: 0.4
    });
    var col = new THREE.Mesh(colGeo, colMat);
    col.position.y = 2.95;
    group.add(col);

    // Pipeline routes (animated pulsing lines)
    var routes = [
      ['supply_scout', 'product_studio', 'lead.approved'],
      ['product_studio', 'storefront', 'listing.drafted'],
      ['storefront', 'treasury', 'shopify.order_paid'],
    ];

    for (var i = 0; i < routes.length; i++) {
      var r = routes[i];
      var srcPos = buildingAvatars[r[0]];
      var dstPos = buildingAvatars[r[1]];
      if (srcPos && dstPos) {
        var sp = srcPos.getWorldPosition(new THREE.Vector3());
        var dp = dstPos.getWorldPosition(new THREE.Vector3());
        sp.y = 2.25; dp.y = 2.25;
        var geometry = new THREE.BufferGeometry().setFromPoints([sp, dp]);
        var lineMat = new THREE.LineBasicMaterial({
          color: PALETTE.accent_blue, transparent: true, opacity: 0.35
        });
        var line = new THREE.Line(geometry, lineMat);
        group.add(line);
        group.userData.routes.push({ line: line, src: r[0], dst: r[1], type: r[2] });
      }
    }

    return group;
  }

  function createConsoleBanks() {
    var group = new THREE.Group();
    var bankGeo = new THREE.BoxGeometry(6, 1.2, 0.4);
    var bankMat = new THREE.MeshStandardMaterial({
      color: PALETTE.panel, roughness: 0.6, metalness: 0.2
    });

    // Front console bank
    var front = new THREE.Mesh(bankGeo, bankMat);
    front.position.set(0, 0.6, -5);
    front.castShadow = true; front.receiveShadow = true;
    group.add(front);

    // Left console bank (rotated)
    var left = new THREE.Mesh(bankGeo, bankMat);
    left.rotation.y = Math.PI / 2;
    left.position.set(-5, 0.6, 0);
    left.castShadow = true; left.receiveShadow = true;
    group.add(left);

    // Right console bank (rotated)
    var right = new THREE.Mesh(bankGeo, bankMat);
    right.rotation.y = Math.PI / 2;
    right.position.set(5, 0.6, 0);
    right.castShadow = true; right.receiveShadow = true;
    group.add(right);

    // Console screen panels with purple glow
    var screenGeo = new THREE.PlaneGeometry(5, 0.8);
    var screenMat = new THREE.MeshStandardMaterial({
      color: PALETTE.accent_purple, emissive: PALETTE.accent_purple,
      emissiveIntensity: 0.2, transparent: true, opacity: 0.5,
      side: THREE.DoubleSide
    });
    var fScreen = new THREE.Mesh(screenGeo, screenMat);
    fScreen.position.y = 0.8;
    fScreen.position.z = -4.4;
    fScreen.rotation.x = 0.15;
    group.add(fScreen);

    return group;
  }

  function animate() {
    if (!scene) return;
    var t = Date.now() * 0.001;

    // Pulse the holotable routes
    if (scene.userData.holoRoutes) {
      scene.userData.holoRoutes.rotation.y += 0.002;
      var routes = scene.userData.holoRoutes.userData.routes || [];
      for (var i = 0; i < routes.length; i++) {
        var opacity = 0.25 + 0.1 * Math.abs(Math.sin(t * 3 + i));
        routes[i].line.material.opacity = opacity;
      }
    }

    // Pulse avatar screens and status lights
    for (var name in buildingAvatars) {
      var avatar = buildingAvatars[name];
      var userData = avatar.userData || {};
      if (userData.screenMat) {
        userData.screenMat.emissiveIntensity = 0.15 + 0.1 * Math.abs(Math.sin(t * 2 + i));
      }
      if (userData.indicatorMat) {
        userData.indicatorMat.emissiveIntensity = 0.3 + 0.2 * Math.abs(Math.sin(t * 2 + i));
      }
    }

    if (controls) controls.update();
    renderer.render(scene, camera);
    if (labelRenderer) labelRenderer.render(scene, camera);
    animationId = requestAnimationFrame(animate);
  }

  function initInterior(buildings) {
    var canvas = ensureCanvas();
    if (!canvas) {
      console.warn('[control_room] no canvas element found');
      return;
    }

    if (!THREE) {
      console.warn('[control_room] THREE.js not loaded');
      return;
    }

    var width = canvas.clientWidth || 400;
    var height = canvas.clientHeight || 300;

    scene = new THREE.Scene();
    scene.background = new THREE.Color(PALETTE.bg);
    scene.fog = new THREE.FogExp2(PALETTE.bg, 0.05);

    camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 50);
    camera.position.set(0, 3.5, 7);
    camera.lookAt(0, 1.5, 0);

    renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;

    // Label renderer
    labelRenderer = new THREE.CSS2DRenderer();
    labelRenderer.setSize(width, height);
    labelRenderer.domElement.style.position = 'absolute';
    labelRenderer.domElement.style.top = '0';
    labelRenderer.domElement.style.left = '0';
    labelRenderer.domElement.style.pointerEvents = 'none';
    canvas.parentElement.appendChild(labelRenderer.domElement);

    // Lights — cool/blue ambient + warm sun
    scene.add(new THREE.AmbientLight(0x223355, 0.4));
    scene.add(new THREE.HemisphereLight(0x8899cc, 0x443322, 0.5));
    var sun = new THREE.DirectionalLight(0xffeedd, 1.5);
    sun.position.set(8, 12, 6);
    sun.castShadow = true;
    sun.shadow.mapSize.set(1024, 1024);
    sun.shadow.camera.near = 1; sun.shadow.camera.far = 30;
    sun.shadow.camera.left = -8; sun.shadow.camera.right = 8;
    sun.shadow.camera.top = 8; sun.shadow.camera.bottom = -8;
    scene.add(sun);

    // A subtle accent light (purple) from the holotable
    var accentLight = new THREE.PointLight(PALETTE.accent_purple, 0.6, 8, 2);
    accentLight.position.set(0, 2.5, 0);
    scene.add(accentLight);

    // Floor — dark grid pattern
    var floorMat = new THREE.MeshStandardMaterial({ color: 0x0a101a });
    var floor = new THREE.Mesh(new THREE.PlaneGeometry(16, 16), floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    scene.add(floor);

    // Grid lines on floor
    var grid = new THREE.GridHelper(16, 32, 0x1a2a3a, 0x0d1421);
    grid.position.y = 0.01;
    grid.material.opacity = 0.25;
    grid.material.transparent = true;
    scene.add(grid);

    // Building avatar stations
    var buildingList = buildings || [
      'city_hall', 'supply_scout', 'product_studio', 'storefront', 'treasury',
      'crypto_trading', 'market_data', 'product_flipping', 'social_affiliates',
      'content_creation', 'content_automation', 'content_analytics',
      'sourcing_research', 'scraper', 'signal', 'shopify',
      'finance_building', 'media_building', 'research_building',
    ];

    for (var i = 0; i < buildingList.length; i++) {
      var name = buildingList[i];
      var color = hashColor(name);
      var avatar = createAvatarStation(name, color, i, buildingList.length);
      scene.add(avatar);
      buildingAvatars[name] = avatar;
    }

    // Console banks
    scene.add(createConsoleBanks());

    // Central holotable with pipeline routes
    var holo = createHolotable(buildingList);
    scene.add(holo);
    scene.userData.holoRoutes = holo;

    // Orbit controls
    if (window.OrbitControls) {
      controls = new THREE.OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.05;
      controls.minDistance = 3;
      controls.maxDistance = 12;
      controls.maxPolarAngle = Math.PI / 2;
      controls.target.set(0, 1.5, 0);
      controls.update();
    }

    // Handle resize
    if (resizeHandler) window.removeEventListener('resize', resizeHandler);
    resizeHandler = function () {
      if (!renderer || !camera) return;
      var w = canvas.clientWidth || 400;
      var h = canvas.clientHeight || 300;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      if (labelRenderer) labelRenderer.setSize(w, h);
    };
    window.addEventListener('resize', resizeHandler);

    isInitialized = true;
    animate();
  }

  function resizeCanvas() {
    if (!renderer || !canvasEl) return;
    var width = canvasEl.clientWidth || 400;
    var height = canvasEl.clientHeight || 300;
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height);
    if (labelRenderer) labelRenderer.setSize(width, height);
  }

  function updateAvatarStatus(name, status) {
    if (!buildingAvatars[name]) return;
    var avatar = buildingAvatars[name];
    avatar.userData.status = status;
    var indicator = avatar.children.find(function (c) {
      return c.userData && c.userData.isStatusLight;
    }) || (avatar.userData.indicatorMat && avatar.children.filter(function (c) {
      return c.material === avatar.userData.indicatorMat;
    })[0]);

    var screenColor = status === 'working' ? PALETTE.working :
                      status === 'error' ? PALETTE.error : PALETTE.idle;
    var screenMat = avatar.userData.screenMat;
    if (screenMat) {
      screenMat.color.setHex(screenColor);
      screenMat.emissive.setHex(screenColor);
    }
    if (avatar.userData.indicatorMat) {
      avatar.userData.indicatorMat.color.setHex(screenColor);
      avatar.userData.indicatorMat.emissive.setHex(screenColor);
    }
  }

  function cleanup() {
    if (animationId) {
      cancelAnimationFrame(animationId);
      animationId = null;
    }
    if (resizeHandler) {
      window.removeEventListener('resize', resizeHandler);
      resizeHandler = null;
    }
    if (labelRenderer) {
      if (labelRenderer.domElement && labelRenderer.domElement.parentNode) {
        labelRenderer.domElement.parentNode.removeChild(labelRenderer.domElement);
      }
      labelRenderer = null;
    }
    if (renderer) {
      renderer.dispose();
      renderer = null;
    }
    if (scene) {
      scene = null;
    }
    buildingAvatars = {};
    isInitialized = false;
    canvasEl = null;
  }

  // ---- Expose ----
  window.ControlRoom = {
    init: initInterior,
    updateStatus: updateAvatarStatus,
    resize: resizeCanvas,
    cleanup: cleanup,
    isReady: function () { return isInitialized; }
  };
})();
