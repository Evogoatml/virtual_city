# Archived code

These files are preserved for reference and are not part of the running Flask application.
They were moved with `git mv` rather than deleted.

## `legacy-city-ui/`

This is the superseded grid UI: `templates/city.html`, `static/city.js`,
`static/city.css`, and `static/control_room.js`. Verification found that the
Flask route table renders only `home.html`, `operator.html`, and `manager.html`;
`city.html` had no route, its CSS/JS were referenced only by that unused page,
and `control_room.js` had no script tag. The active UI is `templates/home.html`
with `static/city_3d.js` and `static/dashboard.js`.

## `legacy-kernel/`

`CEO-kernel/` contains the old CEO kernel tree and `city-kernel-extracted/`
contains its duplicate extracted files. Verification found no imports from
active code; the old registry skip was removed because the tree is no longer
under `buildings/`. The extracted `build_loop.py`, `cognitive_workflow.py`,
`orchestration_patterns.json`, `policy.py`, and `workflow_engine.py` were exact
SHA-256 duplicates of files in the CEO kernel before the move. Direct imports
were also blocked by missing legacy `core`/`brain` modules.

Archive contents are intentionally not imported or served. Restore a file only
with a corresponding import/route test and an explicit review.
