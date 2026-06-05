# Hosted Cadybara API Notes

This note captures the current shared understanding of the public Cadybara
product API. It exists because the repo phrase "online testing" is easy to
misread: in this codebase it currently means the local lab control plane, not
the hosted product API.

## What Is Confirmed

- Public app: `https://app.cadybara.com`
- Public marketing/LLM context: `https://www.cadybara.com/llms.txt`
- Hosted API base discovered from the app bundle:
  `https://api.cadybara.com`
- The app stores browser login data in localStorage keys named
  `prompt_forge_token` and `prompt_forge_user`.
- Authenticated app calls use `Authorization: Bearer <token>`.
- The app's API-key dialog says agent integrations should call:

```text
POST https://api.cadybara.com/api/agent/generate
X-API-Key: <key>
```

- The API-key dialog copy says this endpoint needs no browser login when an
  API key is supplied.
- Unauthenticated `GET https://api.cadybara.com/api/models` returns `401`.
- Unauthenticated `GET https://api.cadybara.com/api/auth/me` returns `401`.
- `GET https://api.cadybara.com/api/agent/generate` returns `405`, which
  confirms the route exists but only accepts other methods.
- Unauthenticated `POST https://api.cadybara.com/api/agent/generate` returns
  `401`, which confirms authentication is required.

## What Is Not Yet Known

Do not implement against guesses for these fields unless the user explicitly
accepts a provisional adapter.

- Exact `POST /api/agent/generate` request body.
- Exact response shape and where generated Python/CadQuery code appears.
- Whether the endpoint returns only source code or also render/export artifacts.
- Whether the endpoint accepts model, temperature, max-token, seed, or mode
  parameters, and what names those fields use.
- Error response shape for invalid prompts, generation failures, rate limits,
  quota exhaustion, and bad API keys.
- Rate-limit headers or usage/quota headers.
- Whether prompt text should be wrapped locally in the repo's CadQuery prompt,
  or whether the hosted endpoint expects raw natural language.

## Public App Routes Found In The Bundle

The app bundle referenced these hosted API routes. They are useful for
orientation, but only `POST /api/agent/generate` is currently known to be
intended for API-key agents.

```text
/api/agent/generate
/api/auth/api-keys
/api/auth/check-username
/api/auth/google-login
/api/auth/invite-link
/api/auth/login
/api/auth/me
/api/auth/register-with-invite
/api/auth/session
/api/chat/build
/api/chat/like
/api/chat/stream
/api/execute
/api/export-glb
/api/export-step
/api/export-stl
/api/import-stl
/api/models
/api/parse-params
/api/projects
/api/projects/{id}
/api/projects/{id}/share
/api/projects/{id}/versions
/api/projects/{id}/versions/{version}
```

## How This Should Fit This Repo

The provider boundary is in `projects/local-running/`:

- `cadybara/providers/base.py` defines `ModelProvider` and `ProviderResponse`.
- `cadybara/providers/ollama.py` is the current real provider example.
- `cadybara/runner.py::provider_for_model()` selects the provider from each
  model config.

A hosted Cadybara integration should therefore be added as a new provider in
`projects/local-running/`, not bolted directly into the lab server.

Recommended future shape once official request/response docs are available:

- Add a `CadybaraApiProvider` implementing `ModelProvider`.
- Read the API key from `CADYBARA_API_KEY`; never commit it or put it in YAML.
- Use `base_url: "https://api.cadybara.com"` in configs so test/staging API
  hosts can be swapped without code changes.
- Use a provider name such as `cadybara_api` to distinguish hosted API rows from
  local `ollama` rows in JSONL.
- Keep CadQuery artifact export and grading local unless the hosted endpoint is
  explicitly documented to return equivalent artifacts.
- Preserve provider failures as JSONL data. A hosted API error should not be
  hidden or converted into a successful CAD result.

## What To Ask The API Owner For

Before writing the hosted provider, get one official example for the agent
endpoint. A complete answer should include:

```bash
curl -X POST "https://api.cadybara.com/api/agent/generate" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $CADYBARA_API_KEY" \
  -d '{ ... exact body ... }'
```

Also ask for:

- A successful JSON response example.
- A bad-key response example.
- A validation-error response example.
- A rate-limit/quota response example.
- Whether the returned source is guaranteed to be CadQuery/Python.
- Whether the server already executes/renders code.

## Verification Commands Used

These commands are safe probes that do not require a key:

```powershell
Invoke-WebRequest -Uri "https://api.cadybara.com/api/models" -UseBasicParsing
Invoke-WebRequest -Uri "https://api.cadybara.com/api/agent/generate" -Method GET -UseBasicParsing
Invoke-WebRequest -Uri "https://api.cadybara.com/api/agent/generate" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"prompt":"Create a phone stand"}' `
  -UseBasicParsing
```

Expected current results:

- `/api/models`: `401 Unauthorized`
- `GET /api/agent/generate`: `405 Method Not Allowed`
- unauthenticated `POST /api/agent/generate`: `401 Unauthorized`

If those results change, update this note before changing the provider plan.

## Verification Snapshot

Last checked from this workspace on 2026-06-05:

- `pytest projects/cadybara-online-testing/tests -q -p no:cacheprovider`:
  `12 passed`
- `pytest projects/local-running/tests -q -p no:cacheprovider`: `36 passed`
- `pytest -q -p no:cacheprovider`: `54 passed`
- Hosted no-key probes matched the expected `401`/`405` statuses above.
- `git diff --check` reported only existing line-ending warnings for tracked
  files in this Windows checkout; it did not report whitespace errors from
  these documentation edits.
