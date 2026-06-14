# Hosted Cadybara Agent API

This note is the current local truth for using the hosted Cadybara product API
from this repo. It is intentionally specific because the phrase "online
testing" is overloaded here: `projects/cadybara-online-testing/` is the local
lab control plane, while `https://api.cadybara.com` is the hosted product API.

## Current Status

As of 2026-06-06 from Arvin's Windows machine:

- `https://api.cadybara.com` is reachable.
- `GET /health` returns `200 {"status":"ok"}`.
- `GET /openapi.json` returns `200` and documents `POST /api/agent/generate`.
- `GET /api/agent/generate` returns `405`, correctly allowing only `POST`.
- `POST /api/agent/generate` without `X-API-Key` returns `401`.
- `POST /api/agent/generate` with a fake API key returns `401 Invalid API key`.
- `POST /api/agent/generate` with Arvin's key and a tiny cube prompt returned
  `200` in about `23.6s`.
- The tiny successful response contained `generated_code`, `stl_base64`,
  `validation`, and `response_mode: "json"`.
- The first wall-planter prompt later returned `200` in about `49.1s`, so the
  real prompt ladder is not categorically blocked.
- Some wall-planter attempts have also produced `504 Gateway Timeout` at about
  `60s` through the hosted load balancer. Treat that as hosted generation
  variability or prompt/model timeout, not local connectivity failure.
- On 2026-06-07 the API owner confirmed the production API sits behind an AWS
  ALB with a 60 second idle timeout and deployed `response_mode: "sse"` to keep
  long generations alive. Retrying the five timed-out wall-planter cells with
  SSE returned hosted STLs for all five in `42.6s` to `96.3s`.
- A later 2026-06-07 rate-limit probe returned `429 RATE_LIMITED` immediately
  for ten attempted calls, with the message `Daily limit reached (15/15
  queries)`. For this key/tier, the observed daily generation limit is 15, not
  20.
- One successful wall-planter `generated_code` imported helper modules named
  `planter` and `bracket`. The hosted STL was still returned, but the source was
  not a standalone local CadQuery script.

Sanitized live diagnostics are stored under:

```text
projects/cadybara-online-testing/workspace/hosted_api_smoke/
```

Do not commit API keys, response bodies with secrets, or workspace diagnostics.

## Base URLs

| Environment | URL |
| --- | --- |
| Local product API | `http://localhost:8008` |
| Production product API | `https://api.cadybara.com` |
| Web app | `https://app.cadybara.com` |

The public marketing/LLM context page has also existed at
`https://www.cadybara.com/llms.txt`.

## Auth Split

There are two auth modes:

- Agent generation uses an API key in `X-API-Key`.
- Browser/session/project/chat/model-management endpoints use JWT bearer auth.

Agent requests:

```http
X-API-Key: pfk_<your-key>
Content-Type: application/json
```

Session endpoints:

```http
Authorization: Bearer <jwt-token>
Content-Type: application/json
```

### Creating An API Key

Use the web app or the JWT endpoints. The full plaintext key is returned once;
store it in a secret store or environment variable, not in YAML.

```http
POST /api/auth/login
Content-Type: application/json

{ "username": "...", "password": "..." }
```

`POST /api/auth/login` returns:

```json
{
  "token": "...",
  "user": {
    "id": "...",
    "username": "...",
    "tier": "..."
  },
  "usage": {}
}
```

Then:

```http
POST /api/auth/api-keys
Authorization: Bearer <token>
Content-Type: application/json

{ "name": "My Agent Key" }
```

The create response includes:

```json
{
  "id": "...",
  "key": "pfk_...",
  "prefix": "pfk_...",
  "name": "My Agent Key",
  "created_at": "..."
}
```

Only `key` is the full plaintext secret.

API key management endpoints require JWT bearer auth:

```http
GET    /api/auth/api-keys
POST   /api/auth/api-keys
DELETE /api/auth/api-keys/{id}
```

`GET /api/models` also requires JWT bearer auth. An agent API key alone is not
expected to work there.

## Agent Endpoint

### `POST /api/agent/generate`

This is equivalent to submitting a prompt in a new chat session in agent mode
and waiting for the whole server-side loop to finish. Internally, the server
runs the same style of agentic workflow as `/api/chat/stream`:

```text
intent -> design -> implement -> validation -> repair/validation if needed -> exit
```

The client does not receive the stream. The endpoint returns the final STL or a
JSON envelope, depending on `response_mode`.

Headers:

| Header | Required | Description |
| --- | --- | --- |
| `X-API-Key` | Yes | Agent API key |
| `Content-Type` | Yes | `application/json` |

Request body:

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `prompt` | string | required | Natural-language description of the model |
| `response_mode` | `"json"`, `"stl"`, or `"sse"` | `"json"` | Structured JSON, binary STL, or server-sent events |
| `model` | string or null | tier default | Optional model ID from the chat model selector |
| `linear_deflection` | number | `0.1` | Mesh density; lower is finer, typical `0.01` to `0.5` |
| `angular_deflection` | number | `0.1` | Angular tolerance in radians, typical `0.01` to `0.5` |

Minimal JSON request:

```json
{
  "prompt": "Create a simple 20 mm cube with rounded edges.",
  "response_mode": "json",
  "linear_deflection": 0.1,
  "angular_deflection": 0.1
}
```

Equivalent PowerShell smoke:

```powershell
$key = [Environment]::GetEnvironmentVariable("CADYBARA_API_KEY", "User")
$body = @{
  prompt = "Create a simple 20 mm cube with rounded edges."
  response_mode = "json"
  linear_deflection = 0.1
  angular_deflection = 0.1
} | ConvertTo-Json

Invoke-WebRequest `
  -Uri "https://api.cadybara.com/api/agent/generate" `
  -Method POST `
  -Headers @{ "X-API-Key" = $key } `
  -ContentType "application/json" `
  -Body $body `
  -UseBasicParsing
```

Known JSON success shape:

```json
{
  "generated_code": "import cadquery as cq\n...",
  "stl_base64": "...",
  "validation": {
    "valid": true,
    "confidence": 1.0,
    "issues": [],
    "brief_reason": "..."
  },
  "response_mode": "json"
}
```

`response_mode: "stl"` returns a binary STL response instead of the JSON
envelope. That is useful for product consumers but not ideal for this repo's
source-code grading path, because the local harness grades and artifacts around
CadQuery source.

`response_mode: "sse"` streams progress, heartbeat, export, and final result
events. The final `type: "result"` event has the same `generated_code`,
`stl_base64`, `validation`, and `response_mode` fields as JSON mode. Use SSE
for this repo's hosted smoke runs because it avoids the production ALB's
60-second idle timeout while still giving the harness source code and STL bytes.

## Repo Integration

Hosted API support belongs at the provider boundary:

```text
projects/local-running/cadybara/providers/cadybara_api.py
```

The provider is selected with:

```yaml
models:
  - name: "cadybara-agent-default"
    provider: "cadybara_api"
    base_url: "https://api.cadybara.com"
    timeout_seconds: 75
    response_mode: "sse"
```

Use `name: "cadybara-agent-default"` to omit the optional `model` field and let
the server pick the tier default. To force a hosted model ID, set:

```yaml
hosted_model_id: "<model-id-from-chat-selector>"
```

The provider reads the secret from `CADYBARA_API_KEY` by default. On Windows, it
also falls back to the User environment value if the current process did not
inherit it. Do not put the key in config files.

The runner still uses `output_mode: "cadquery"` so generated source flows
through the same local artifact/export/review/grading path as Ollama runs. For
`provider: cadybara_api`, the runner posts the raw natural-language design
request instead of this repo's CadQuery instruction template. The provider also
keeps an unwrap guard for direct/manual calls. It returns `generated_code` as
the provider output.

The provider also preserves `stl_base64` from the hosted response. Artifact
writing stores that STL as `hosted_model.stl`; if local execution of
`generated_code` fails because the source is multi-file or imports server-only
helpers, the row still records `render_error.txt` while exposing the hosted STL
for viewing. Do not erase the local source failure to make the row look cleaner.

The active hosted smoke config is:

```text
projects/cadybara-online-testing/configs/online_smoke.yaml
```

It uses the five active wall-planter prompts in:

```text
projects/cadybara-online-testing/prompts/wall_planter_agent_prompts.yaml
```

Follow-on hosted review batches live in the same config folder as dated
experiment records: wall-planter blind repeats, snowman prompts, hook prompts,
and gapfill/hook/snowman mixes. Keep them separate unless the researcher asks
for a new combined experiment; derived blind-review summaries belong in
`projects/cadybara-online-testing/workspace/reviews/`.

The current shareable hosted smoke snapshot is:

```text
results/cadybara_online_smoke_reps2/20260606_163617_windows/
```

## Current Risk

The hosted endpoint works for a tiny cube prompt and for all ten current
wall-planter smoke cells when using `response_mode: "sse"`. Plain JSON mode
previously hit load-balancer `504` around `60s` on five cells. Treat any future
60-second JSON-mode failure as a transport/gateway issue first, then retry with
SSE before changing prompts. The likely next questions for the API owner are:

- Which model IDs are available for this API key/tier?
- Is there a cheaper/faster model suitable for smoke testing?
- Are rate-limit or usage headers exposed on agent responses?
- Is `generated_code` supposed to be a standalone single-file CadQuery script,
  or can it reference server-side helper modules while `stl_base64` remains the
  authoritative export?

## Manual Diagnostics

No-key and fake-key probes are safe:

```powershell
Invoke-WebRequest -Uri "https://api.cadybara.com/health" -UseBasicParsing
Invoke-WebRequest -Uri "https://api.cadybara.com/openapi.json" -UseBasicParsing
Invoke-WebRequest -Uri "https://api.cadybara.com/api/agent/generate" -Method GET -UseBasicParsing
Invoke-WebRequest `
  -Uri "https://api.cadybara.com/api/agent/generate" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"prompt":"Create a phone stand"}' `
  -UseBasicParsing
```

Expected unauthenticated results:

- `/health`: `200`
- `/openapi.json`: `200`
- `GET /api/agent/generate`: `405`
- no-key `POST /api/agent/generate`: `401`

Run the hosted config through the normal CLI:

```bash
cadybara run projects/cadybara-online-testing/configs/online_smoke.yaml
```

For a one-cell smoke while debugging:

```bash
cadybara run projects/cadybara-online-testing/configs/online_smoke.yaml --limit 1 --retry-errors
```

If the key was pasted into chat or screenshots, rotate it after debugging.
