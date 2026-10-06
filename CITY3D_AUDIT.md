# CITY3D_AUDIT

## 1. RENDERING STACK

**Short answer:** The home page already renders a 3D city with **Three.js**. The home template also includes an import map and loads the 3D module plus shared dashboard code. On the operator page, there is also a separate **raw WebGL** background, but that is not the home page.

**Evidence**
- `templates/home.html:7-15` defines an import map with `three`, `three/addons/`, and `tween`.
- `templates/home.html:395-397` loads `dashboard.js`, Tween, and `static/city_3d.js` as a module.
- `static/city_3d.js:1-6` imports `THREE`, `OrbitControls`, `CSS2DRenderer`, `EffectComposer`, `RenderPass`, and `UnrealBloomPass`.
- `static/city_3d.js:35-69` creates the scene, camera, renderer, composer, label renderer, and orbit controls.
- `static/city_3d.js:180-234` creates building meshes and CSS2D labels.
- `templates/operator.html:306-355` contains a separate `initWebGL()` function using `canvas.getContext('webgl')` for an ambient background, but this is on `/operator`, not `/`.

**Is 3D already rendered on `/`?**
- Yes: Three.js.

**Home page JS loaded, in order**
1. `static/dashboard.js` (`templates/home.html:395`)
2. `https://unpkg.com/@tweenjs/tween.js@18.6.4/dist/tween.umd.js` (`templates/home.html:396`)
3. `static/city_3d.js` as a module (`templates/home.html:397`)

## 2. EXISTING 3D CODE

**Short answer:** There is already a full Three.js city scene with camera controls, mesh creation, raycasting, bloom, labels, and a building-enter interaction. The “enter building” flow is a **3D interior scene + camera move**, not just a 2D overlay.

**Evidence: scene / camera / renderer / controls / raycaster**
- `static/city_3d.js:35-69` creates `scene`, `PerspectiveCamera`, `WebGLRenderer`, `EffectComposer`, `CSS2DRenderer`, and `OrbitControls`.
- `static/city_3d.js:305-315` creates a `Raycaster` and hit-testing for building clicks.
- `static/city_3d.js:516-517, 977-993` runs the render loop and updates controls / composer.

**Evidence: scene geometry and meshes**
- `static/city_3d.js:86-130` builds ground, roads, and trees.
- `static/city_3d.js:180-234` creates the actual building meshes, roof, rings, glow, and CSS2D labels.

**Evidence: enter-building interaction**
- `templates/home.html:335-337` includes hidden `#interior-display`, `#enter-building`, and `#exit-building` elements.
- `static/city_3d.js:322-327` binds double-click to `enterBuilding(name)`.
- `static/city_3d.js:334-385` implements `enterBuilding(name)` by removing exterior buildings, creating an interior room, tweening the camera, and fetching `/api/building/<name>/dashboard`.
- `static/city_3d.js:387-415` implements `exitBuilding()` to restore the exterior city and tween the camera back out.
- `static/city_3d.js:432-514` builds the interior room geometry with walls, ceiling, panels, pedestal, and label.

**What already works**
- The city is already a live 3D scene, not a 2D mock.
- Buildings are individually pickable via raycasting.
- Orbit controls already exist.
- There is already an interior/enter-building experience with camera transitions and a dedicated room.
- The inspector/dashboard already consumes `/api/building/<name>/dashboard`.

## 3. API CONTRACTS

**Short answer:** `/api/city` returns the full city state from `get_city_state(conn)`. `/api/stream` is SSE that emits the same city-state JSON as `data: ...` events, with `: keep-alive` comments between unchanged payloads. `/api/agent/<name>` returns agent detail JSON, and `/api/building/<name>/dashboard` returns a richer dashboard payload.

### `/api/city`
**Handler**
- `app.py:295-300` returns `jsonify(get_city_state(conn))`.

**Shape**
- The route returns whatever `city.city_grid.get_city_state(conn)` produces; the exact schema is not spelled out in `app.py`.
- Evidence that the frontend expects a top-level object with `buildings` and optional `districts`, `streets`, `north_star`, and `brain_notes`:
  - `static/city_3d.js:876-908` reads `data.buildings || data`.
  - `static/city_3d.js:261-304` reads `state.districts` and `state.streets` for overlays.
  - `templates/operator.html:172-199` expects `state.buildings` and counts statuses.

**Example agent / building entry shape used by the home page**
From the home-page renderer, each building object includes at least:
- `name`
- `subject`
- `district`
- `status`
- `paused`
- `x`, `y`, `w`, `h`
- `color`
- `departments`
- `autonomy` / `autonomy_level`-derived UI state

Evidence:
- `static/city_3d.js:180-234` uses `data.name`, `data.subject`, `data.x`, `data.y`, `data.w`, `data.h`, `data.color`, `data.status`, and `data.paused`.
- `static/city_3d.js:876-908` and `templates/operator.html:172-199` both treat the city payload as a list under `buildings`.

### `/api/stream`
**Handler**
- `app.py:724-745` returns `Response(gen(), mimetype='text/event-stream')`.
- `app.py:728-741` shows the event payload logic.

**SSE event names / fields**
- This endpoint emits only **default SSE messages** via `data: <json>\n\n`.
- It does **not** set custom `event:` names in the code.
- When the payload is unchanged, it emits `: keep-alive\n\n` comment frames.

**Payload shape**
- The `data:` field is `json.dumps(state, sort_keys=True)` where `state = get_city_state(conn)`.
- Therefore, the SSE payload shape matches `/api/city`.

### `/api/agent/<name>`
**Handler**
- `app.py:302-334`.

**Returned JSON shape**
```json
{
  "name": "<agent name>",
  "subject": "<subject>",
  "district": "<district>",
  "autonomy": "<autonomy level or error object>",
  "paused": false,
  "skills": [
    {
      "name": "<skill name>",
      "risk": "<risk>",
      "cost": "<cost kind>",
      "event": "<event>",
      "description": "<description>"
    }
  ],
  "report": {},
  "recent_events": [],
  "cognitive": {}
}
```
- Evidence: `app.py:316-334`.
- Note: `autonomy`, `report`, `recent_events`, and `cognitive` are wrapped through a helper that may return `{"_error": ...}` on failure (`app.py:310-315`).

### `/api/building/<name>/dashboard`
**Handler**
- `app.py:353-571`.

**Returned JSON shape**
Top-level baseline fields:
```json
{
  "name": "<agent name>",
  "subject": "<subject>",
  "report": {},
  "events": [],
  "cognitive": {},
  "chronolog": [],
  "traces": []
}
```
- Evidence: `app.py:362-381`.

Per-building extensions are conditionally added, such as:
- `positions`, `total_pnl`, `total_trades` for `crypto_trading` (`app.py:392-405`)
- `inventory` for `product_flipping` (`app.py:406-414`)
- `campaigns` for `social_affiliates` (`app.py:415-423`)
- `pipeline` for `content_creation` (`app.py:424-431`)
- `queue` for `content_automation` (`app.py:433-440`)
- `videos` for `content_analytics` (`app.py:442-449`)
- `leads` for `sourcing_research` (`app.py:451-458`)
- `prices` for `market_data` (`app.py:460-467`)
- `ledger` for `finance_treasury` (`app.py:469-476`)
- `meetings` for `city_hall` (`app.py:478-485`)
- `alerts` for `signal` (`app.py:487-496`)
- `scans` and `service` / `service_error` for `web_check` (`app.py:499-511`)
- nested building reports for `finance_building`, `media_building`, `research_building`, `neural_index`, `scraper`, and `controll_panel` (`app.py:512-569`)

## 4. AUTH

**Short answer:** Yes. `CITY_API_KEY` is enforced for mutating routes when the environment variable is set. The expected header is `X-City-Api-Key`. The code also allows `?api_key=` as a fallback query parameter.

**Evidence**
- `README.md:47-48` says mutating API routes may require `X-City-Api-Key` when `CITY_API_KEY` is set.
- `app.py:30-57` implements the check and header name.
- `app.py:54-56` returns `{"error": "unauthorized", "hint": "set X-City-Api-Key header"}` when missing or wrong.

**Routes protected by the key logic**
`app.py:31-40` lists these mutating prefixes:
- `/api/query`
- `/api/meeting`
- `/api/plan`
- `/api/budget/pause`
- `/api/budget/resume`
- `/api/webcheck/`
- `/api/agent/`
- `/api/escalations/`
- `/api/shopify/automate/`

**Note on route coverage**
- Because the guard is prefix-based and only applies to non-GET/HEAD/OPTIONS requests, any POST/PUT/etc. under those prefixes is protected.
- Some routes in the file are mutating but outside the listed prefixes and therefore are not covered by this guard as written.

## 5. STATIC ASSET PIPELINE

**Short answer:** Yes, the home template already uses an import map. There are no vendored JS files under `static/vendor/` in the active surfaced code we inspected, and the root Flask app does not have a root npm/package.json script pipeline. The nested Node apps are explicitly separate.

**Evidence**
- Import map: `templates/home.html:7-15`.
- Root Flask app has no root Vite/React build: `README.md:3-6`.
- Nested Node apps are separate and not part of root Flask build: `README.md:73-83`.
- The active frontend scripts are plain static files loaded by Jinja: `templates/home.html:395-397`.

**Vendored JS under `static/vendor/`**
- No evidence found in the inspected files.
- If you need a full repo-wide check, search the `static/vendor/` path directly.

**Root npm/package.json script for the Flask app**
- No root npm pipeline is described in the repo docs we inspected.
- The README explicitly says the browser UI is server-rendered HTML plus static JavaScript and that there is no root Vite/React build (`README.md:3-6`).

## 6. CONFLICTS / RISKS

**Short answer:** The main risks to adding Three.js are low, because it is already in use. The bigger risk is mixing the existing 3D scene with other page-specific rendering patterns or assuming the operator page’s raw WebGL code is the home page stack. Also, the home template currently relies on CDN imports via importmap and unpkg, so offline/network policy could matter.

**Evidence / risk notes**
- Three.js is already established on `/` via `templates/home.html:7-15` and `static/city_3d.js:1-69`.
- The home page already has template-driven 3D UI chrome and hidden inspector elements (`templates/home.html:334-397`), so replacing it would likely break existing interactions.
- The page depends on external CDN modules from unpkg (`templates/home.html:10-12`, `templates/home.html:396`), which can fail under strict CSP or offline conditions.
- The operator page uses a separate raw WebGL overlay (`templates/operator.html:306-355`), so there are already two rendering paradigms in the repo.
- The `home.html` template has a hidden `interior-display`, `enter-building`, and `exit-building` flow wired by `static/city_3d.js` (`templates/home.html:335-337`, `static/city_3d.js:334-415`), so any new scene should preserve those hooks.

**Known quirks observed**
- `templates/home.html` loads `dashboard.js` before `city_3d.js` (`templates/home.html:395-397`), so any new code should continue to expect `dash(...)` to exist.
- The 3D scene uses `CSS2DRenderer`, `EffectComposer`, and `OrbitControls`, so a new rendering layer must not shadow or reinitialize the same canvas/container unexpectedly.

**Recommendation**
Use Three.js
