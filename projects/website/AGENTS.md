# AGENTS.md - Website

You are in `projects/website/`, the static browser side of Cadybara. Your job
is to improve the landing page, project dashboard, hosted review board, CAD and
voxel diffusion training pages, visual assets, vanilla JS behavior, and Three.js
viewer without drifting into the Python runner or lab API implementation.

Read this file like a note from someone who just worked here: the most important
thing is not just "keep it vanilla." It is to keep the interface honest about
what it actually knows.

## Read First

Read these before editing:

1. Root `AGENTS.md`
2. Root `COMMON.md`
3. `projects/website/README.md`
4. The file you are about to change

For dashboard or landing work, also read:

- `projects/website/lab/index.html`
- `projects/website/lab/styles.css`
- `projects/website/lab/landing.js`
- `projects/website/lab/dashboard.html`
- `projects/website/lab/dashboard.css`
- `projects/website/lab/dashboard.js`

For CAD diffusion page work, also read:

- `projects/website/lab/cad-diffusion.html`
- `projects/website/lab/cad-diffusion.css`
- `projects/website/lab/cad-diffusion.js`
- `projects/cadybara-online-testing/cadybara_online_testing/lab_server.py`

For voxel diffusion or hosted review work, also read:

- `projects/website/lab/voxel-diffusion.html`
- `projects/website/lab/voxel-diffusion.css`
- `projects/website/lab/voxel-diffusion.js`
- `projects/website/lab/hosted-review.html`
- `projects/website/lab/hosted-review.css`
- `projects/website/lab/hosted-review.js`
- `projects/cadybara-online-testing/cadybara_online_testing/lab_server.py`
- `projects/cadybara-online-testing/cadybara_online_testing/reviews.py`

For viewer work, also read:

- `projects/website/viewer/index.html`
- `projects/website/viewer/styles.css`
- `projects/website/viewer/app.js`
- The artifact path producer in `projects/local-running/` if your change
  touches generated artifact URLs.

## Boundaries

Do:

- Keep HTML/CSS/JS static and vanilla.
- Use the lab APIs owned by `projects/cadybara-online-testing/`.
- Update this folder's docs when UI purpose or route contracts change.
- Use real image assets for pixel-art or sprite-led UI.
- Keep viewer compatibility with `?artifact=...` and `?stl=...`.

Do not:

- Add React, Vue, Vite, Next, Svelte, Tailwind build steps, or frontend package
  plumbing.
- Add FastAPI, SQLAlchemy, or backend route logic from this folder.
- Duplicate Python lab-server behavior in browser JS.
- Edit runner behavior unless the user explicitly asks for a coordinated
  cross-project change.
- Commit `projects/website/logs/` output as source.
- Delete or rewrite generated/baseline workspace data.

Cross-project changes are allowed only when a public contract moves. If you
change an API expectation in the website, update
`projects/cadybara-online-testing/` docs/tests in the same focused change.

## Current Surfaces

- `/lab/`
  - Pixel-art landing page.
  - Demo localStorage auth only.
  - Routes to `dashboard.html`.
- `/lab/dashboard.html`
  - Stable project library / object-family picker.
  - Not a live run dashboard.
- `/lab/cad-diffusion.html`
  - Live CAD diffusion training status page.
  - Polls `/api/cad-diffusion/status`.
  - Posts start/stop to CAD diffusion endpoints.
- `/lab/voxel-diffusion.html`
  - Live voxel diffusion training status page.
  - Polls `/api/voxel-diffusion/status`.
  - Posts start/stop to voxel diffusion endpoints.
- `/lab/hosted-review.html`
  - Hosted API review board for saved STL attempts.
  - Supports blind mode and combined config review sessions.
- `/viewer/`
  - Three.js viewer for JSON artifacts and STL meshes.
- `lab/app.js`
  - Preserved richer lab control/review UI.
  - Currently unlinked from routed HTML.

## Dashboard Rule

This is the rule most likely to save you from making the page worse:

**The dashboard is a stable project library, not live telemetry.**

Do not add fake changing information such as:

- active counts
- review counts
- queued counts
- `Running`, `Queued`, `Paused`, `Ready`, `Draft`
- `Review ready`
- render totals
- average scores
- "today", "yesterday", or date stamps
- "last run"

The dashboard should use stable concepts instead:

- object family
- focus
- intended use
- review surface
- prompt/design concerns
- short tags like `mounting`, `vents`, `curves`, `tolerance`

The current dashboard has 9 object-family cards and a selected focus panel.
`New project` selects the open slot and scrolls it into view. It does not create
server data.

## Design Judgment

Cadybara should feel:

- bright
- clean
- blue/green
- mossy
- lively
- local-lab practical
- a little playful without becoming noisy

When a page feels too "AI generated," the fix is usually less fake gloss and
more specificity:

- clearer hierarchy
- fewer giant decorative objects
- stable text that does not overpromise
- reusable real assets
- controls that look like they do something concrete

Avoid:

- dark glassmorphism
- one-note blue/purple gradients
- muddy brown/orange themes
- generic game buttons
- decorative blobs/orbs
- copy that explains features the page does not actually have
- CSS pretending to be sprites when bitmap assets already exist

## Assets

Use `projects/website/lab/assets/` for reusable visual assets.

Currently important:

- `ai-cad-pixel-capybara-build-crew.png`
  - landing hero image
- `cadybara-dashboard-bg.png`
  - dashboard/CAD diffusion background world
- `project-stones/project-stone-1.png` through `project-stone-9.png`
  - dashboard project identity assets
- sprite sheets and saved images
  - preserve unless the user asks for cleanup

If you generate new bitmap assets, put them in `lab/assets/` with descriptive
names. Do not hide them in temp folders if the UI depends on them.

## API Expectations

The CAD diffusion page uses:

- `GET /api/cad-diffusion/status`
- `POST /api/cad-diffusion/train/start`
- `POST /api/cad-diffusion/train/stop`

The voxel diffusion page uses:

- `GET /api/voxel-diffusion/status`
- `POST /api/voxel-diffusion/train/start`
- `POST /api/voxel-diffusion/train/stop`

The hosted review page uses:

- `GET /api/review`
- `POST /api/review/score`

The preserved `lab/app.js` richer surface expects:

- `GET /api/status`
- `GET /api/run_status`
- `GET /api/current_snapshot`
- `GET /api/results`
- `GET /api/review`
- `POST /api/review/score`
- `POST /api/run/start`
- `POST /api/run/stop`
- `POST /api/models/start`

Do not make the landing or dashboard depend on those richer APIs unless you are
deliberately wiring the richer lab surface back in.

## Verification Checklist

After UI edits:

1. Start a lab server from the repo root.

   ```bash
   cadybara lab --host 127.0.0.1 --port 8790
   ```

2. If Windows returns quietly, check the socket before assuming the server
   failed.

   ```powershell
   Get-NetTCPConnection -LocalPort 8790 -State Listen
   ```

3. Check served routes.

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

4. Check JS syntax.

   ```bash
   node --check projects/website/lab/landing.js
   node --check projects/website/lab/dashboard.js
   node --check projects/website/lab/cad-diffusion.js
   node --check projects/website/lab/voxel-diffusion.js
   node --check projects/website/lab/hosted-review.js
   node --check projects/website/viewer/app.js
   ```

5. For dashboard edits, run the volatile-copy scan from
   `projects/website/README.md`. Expected result: no output.

6. Use browser inspection/screenshots when available. Check desktop and mobile.
   Make sure there is no horizontal overflow, overlapping text, or console
   error.

7. If API assumptions changed, run focused tests:

   ```bash
   python -m pytest projects/cadybara-online-testing/tests/test_lab_endpoints.py projects/cadybara-online-testing/tests/test_lab_server.py -q -p no:cacheprovider
   ```

8. Finish with:

   ```bash
   git diff --check
   ```

## Known Quirks

- Browser automation in the Codex app may time out or lose the Browser plugin
  cache path. If route checks and syntax checks pass but Browser is flaky,
  report that clearly and retry later.
- `lab/app.js` contains a lot of useful richer UI logic, but it is not currently
  attached to a page. Do not assume it is the active dashboard.
- The default `/api/run_status` route was verified returning 200 on
  2026-06-05. If it regresses, check the active online config and Pydantic
  schema before blaming the website.
- Runtime logs under `projects/website/logs/` may be large and old. They are
  historical context at best.

## Personal Handoff

If you only remember one thing from this file, remember this: make the UI feel
truthful. Cadybara can be playful and cute, but the moment it pretends to know
live status it does not have, it starts feeling cheap. Prefer stable,
research-lab-specific language over shiny SaaS filler. The good version of this
site is calm, bright, specific, and useful.
