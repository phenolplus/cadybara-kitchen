# Website

`projects/website/` is the browser-facing Cadybara experience. It is static
HTML/CSS/JS served directly by the Python lab server in
`projects/cadybara-online-testing/`. There is no frontend build step, package
manager, bundler, router library, React/Vue layer, or separate Node server.

If you are an AI arriving cold: this folder is not a marketing site and it is
not a full product shell yet. It is a small, deliberately static browser
surface for a local AI CAD research lab. Keep it honest, bright, usable, and
calm.

This is its own frontend project. It consumes lab APIs and artifact URLs, but it
does not own Python runner behavior, model training, review storage, or hosted
API calls.

## Current State As Of 2026-06-13

The live routed pages are:

- `/lab/`
  - `lab/index.html`, `lab/styles.css`, `lab/landing.js`
  - Pixel-art landing page with demo-only localStorage auth.
  - `Start now` / sign-in / register eventually routes to `dashboard.html`.
- `/lab/dashboard.html`
  - `lab/dashboard.html`, `lab/dashboard.css`, `lab/dashboard.js`
  - Stable project library / object-family picker.
  - It does not show live run state, counts, scores, render totals, queues, or
    dates. This is intentional.
- `/lab/cad-diffusion.html`
  - `lab/cad-diffusion.html`, `lab/cad-diffusion.css`,
    `lab/cad-diffusion.js`
  - CAD diffusion training status page with start/stop controls.
  - This page does call live lab APIs because those controls are actually wired.
- `/lab/voxel-diffusion.html`
  - `lab/voxel-diffusion.html`, `lab/voxel-diffusion.css`,
    `lab/voxel-diffusion.js`
  - Geometry-native voxel diffusion training status page with start/stop
    controls.
  - This page calls live lab APIs for voxel dataset readiness and training.
- `/viewer/`
  - `viewer/index.html`, `viewer/styles.css`, `viewer/app.js`
  - Three.js viewer for JSON part artifacts and STL meshes.
- `/lab/hosted-review.html`
  - `lab/hosted-review.html`, `lab/hosted-review.css`,
    `lab/hosted-review.js`
  - Hosted API review board for saved STL attempts.
  - Supports combined configs with `extra_config=...` and a blind randomized
    judging mode with `mode=blind`.

Preserved but currently unlinked:

- `lab/app.js`
  - A much richer lab control/review surface for run/model/results/snapshot
    APIs.
  - It is not loaded by `index.html`, `dashboard.html`, or
    `cad-diffusion.html` and `voxel-diffusion.html`.
  - Treat it as a preserved interface, not dead code. Wire it back only as a
    deliberate task with matching HTML and API verification.

## Ownership

This folder owns:

- static UI markup, CSS, vanilla browser JS, and visual assets
- landing page and demo localStorage auth
- dashboard project library presentation
- CAD diffusion training page presentation and browser polling behavior
- voxel diffusion training page presentation and browser polling behavior
- Three.js viewer presentation and browser-side artifact loading
- reusable bitmap/sprite assets under `lab/assets/`

This folder does not own:

- Python lab endpoints or endpoint contracts
- run start/stop semantics
- model queue/pull behavior
- CadQuery execution
- append-only JSONL records, reviews, grades, or CAD diffusion datasets

Those belong to `projects/cadybara-online-testing/`,
`projects/local-running/`, and `projects/cad-diffusion/`.

## Mental Model

The website has three different levels of "realness":

1. The landing page is a static first impression plus demo auth. It should feel
   alive and Cadybara-specific, but it is not a real account system.
2. The dashboard is a stable object-family picker. It should help the user
   choose a project direction without pretending to know live experiment state.
3. The CAD diffusion page and viewer are wired tools. They can show live status
   or loaded artifacts because they have concrete API/file contracts.

This distinction matters. When the UI does not actually have live data, do not
invent labels like `Active`, `Running`, `Queued`, `Review ready`, render counts,
averages, or dates. That was tried, and it made the page feel like fake AI
software. Stable project descriptors are better: object type, focus, use, and
surface.

## Dashboard Design Notes

The dashboard was redesigned from a set of large floating stone buttons into a
calmer project library:

- The background art is still the Cadybara world, but it is muted behind a
  clean app surface.
- The existing `project-stones/*.png` assets are reused as smaller identity
  elements inside cards and the focus panel.
- Project cards use stable object-family descriptors:
  - `Benchmark object`
  - `Structural part`
  - `Product shell`
  - `Ergonomic form`
  - `Mounting system`
  - `Storage object`
  - `Clamp fixture`
  - `Manufacturing aid`
  - `Open slot`
- The selected focus panel shows:
  - `Focus`
  - `Use`
  - `Surface`
- `New project` selects and scrolls to the open slot. It does not create data.

If you extend the dashboard, keep this principle: **stable library, not live
telemetry**. Only add live state after an actual API contract exists and the UI
has a clear reason to show it.

## API Contracts

The lab server maps static routes in
`projects/cadybara-online-testing/cadybara_online_testing/lab_server.py`:

- `/`, `/lab`, `/lab/` -> `projects/website/lab/index.html`
- `/lab/<file>` -> `projects/website/lab/<file>`
- `/viewer`, `/viewer/` -> `projects/website/viewer/index.html`
- `/viewer/<file>` -> `projects/website/viewer/<file>`

Live pages currently use these APIs:

- CAD diffusion page:
  - `GET /api/cad-diffusion/status`
  - `POST /api/cad-diffusion/train/start`
  - `POST /api/cad-diffusion/train/stop`
- Voxel diffusion page:
  - `GET /api/voxel-diffusion/status`
  - `POST /api/voxel-diffusion/train/start`
  - `POST /api/voxel-diffusion/train/stop`
- Preserved richer lab surface in `lab/app.js`:
  - `GET /api/status`
  - `GET /api/run_status`
  - `GET /api/current_snapshot`
  - `GET /api/results`
  - `GET /api/review`
  - `POST /api/review/score`
  - `POST /api/run/start`
  - `POST /api/run/stop`
  - `POST /api/models/start`
- Hosted review page:
  - `GET /api/review?config=...`
  - `POST /api/review/score`

The viewer supports:

- `/viewer/?artifact=/path/to/part.json`
- `/viewer/?stl=/path/to/model.stl`
- manual JSON file loading through the `Load JSON` control

Keep viewer links compatible with both `?artifact=...` and `?stl=...`.

## Visual Direction

Keep the Cadybara aesthetic:

- bright
- clean
- blue/green
- mossy
- lively
- a little playful, but still a working lab

Avoid:

- dark/glassy dashboards
- muddy brown palettes
- generic game-button styling
- fake status/telemetry
- CSS-only "sprites" when the design calls for actual pixel art
- oversized decorative cards nested inside other cards

Use real assets from `lab/assets/` for key visual elements. If you generate or
extract reusable sprites, keep them under `lab/assets/` so later screens can use
them too.

## File Map

- `lab/index.html`
  - Landing page shell.
- `lab/styles.css`
  - Landing page styles. It also contains some older unused app-preview styles;
    inspect before deleting.
- `lab/landing.js`
  - Demo auth and localStorage session routing.
- `lab/dashboard.html`
  - Stable project library markup.
- `lab/dashboard.css`
  - Dashboard layout, project cards, focus panel, responsive behavior.
- `lab/dashboard.js`
  - Dashboard card selection and localStorage sign-out.
- `lab/cad-diffusion.html`
  - CAD diffusion training page markup.
- `lab/cad-diffusion.css`
  - CAD diffusion page layout and training status surface.
- `lab/cad-diffusion.js`
  - Polls CAD diffusion status and posts start/stop.
- `lab/voxel-diffusion.html`
  - Voxel diffusion training page markup.
- `lab/voxel-diffusion.css`
  - Voxel diffusion page layout and training status surface.
- `lab/voxel-diffusion.js`
  - Polls voxel diffusion status and posts start/stop.
- `lab/hosted-review.html`
  - Hosted API review board markup.
- `lab/hosted-review.css`
  - Hosted review board layout.
- `lab/hosted-review.js`
  - Loads review cells, supports blind mode, and posts scores.
- `lab/app.js`
  - Preserved richer run/review/model UI; currently unlinked.
- `lab/assets/`
  - Hero art, dashboard background, project stone assets, sprite sheets.
- `viewer/index.html`
  - Fullscreen viewer shell and Three.js import map.
- `viewer/styles.css`
  - Viewer HUD/status styling.
- `viewer/app.js`
  - Three.js scene, JSON artifact renderer, STL renderer, orbit controls.
- `logs/`
  - Historical/local logs. Do not treat as source.

## Verification

Start the lab server from the repo root. Use any free port:

```bash
cadybara lab --host 127.0.0.1 --port 8790
```

If the wrapper behaves oddly on Windows, check the port directly instead of
assuming it failed:

```powershell
Get-NetTCPConnection -LocalPort 8790 -State Listen
```

Minimum route checks:

```powershell
$port = 8790
$paths = @(
  "/lab/",
  "/lab/dashboard.html",
  "/lab/cad-diffusion.html",
  "/lab/voxel-diffusion.html",
  "/lab/hosted-review.html",
  "/viewer/",
  "/api/cad-diffusion/status",
  "/api/voxel-diffusion/status",
  "/api/run_status"
)
foreach ($path in $paths) {
  Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port$path" -TimeoutSec 12 |
    Select-Object StatusCode, RawContentLength
}
```

JavaScript syntax checks:

```bash
node --check projects/website/lab/landing.js
node --check projects/website/lab/dashboard.js
node --check projects/website/lab/cad-diffusion.js
node --check projects/website/lab/voxel-diffusion.js
node --check projects/website/lab/hosted-review.js
node --check projects/website/viewer/app.js
```

Dashboard copy check:

```powershell
$html = (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8790/lab/dashboard.html").Content
$volatile = @(
  "Active", "Review ready", "Running", "Queued", "Paused", "Draft",
  "renders", "avg", "Today", "Yesterday", "Recent", "Last run", "Signal",
  "data-status", "data-updated", "data-renders", "data-signal"
)
$volatile | Where-Object { $html -match [regex]::Escape($_) }
```

Expected result for the dashboard copy check: no output.

When API assumptions are involved, run focused lab tests or the full suite from
the repo root:

```bash
python -m pytest projects/cadybara-online-testing/tests/test_lab_endpoints.py projects/cadybara-online-testing/tests/test_lab_server.py -q -p no:cacheprovider
pytest -q -p no:cacheprovider
```

Also run:

```bash
git diff --check
```

## Last Verification Notes

Verified on 2026-06-05 with a temporary lab server on port `8791`:

- `/lab/` -> 200
- `/lab/dashboard.html` -> 200
- `/lab/cad-diffusion.html` -> 200
- `/viewer/` -> 200
- `/lab/dashboard.css?v=project-studio2` -> 200
- `/lab/dashboard.js?v=project-studio2` -> 200
- `/api/cad-diffusion/status` -> 200
- `/api/run_status?config=projects/local-running/configs/example.yaml` -> 200
- `/api/run_status` -> 200
- Dashboard served HTML contained 9 project cards.
- Dashboard volatile-copy scan returned no matches.
- `node --check` passed for landing, dashboard, CAD diffusion, and viewer JS.
- `python -m pytest projects/cadybara-online-testing/tests/test_lab_endpoints.py projects/cadybara-online-testing/tests/test_lab_server.py -q -p no:cacheprovider` passed: 8 tests.

Browser automation in the Codex app can occasionally time out or lose its
plugin cache path. When that happens, do not treat it as proof that the site is
broken. Use HTTP route checks, JS syntax checks, and then retry browser
inspection once the Browser plugin is available.
