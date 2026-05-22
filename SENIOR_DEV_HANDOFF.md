# Senior Dev Handoff: cadybara-kitchen

Prepared as an engineering handoff for a senior technical lead.

## 1. Executive Summary

`cadybara-kitchen` is intended to become a research framework for studying how prompt wording affects AI-generated CAD model quality.

The core research question is:

> When two prompts mean the same thing, do AI-CAD systems generate equivalent geometry?

The second major question is:

> When a short CAD prompt is expanded into a more detailed engineering specification, which expansions improve output quality and which make it worse?

Current state: the repository is documentation-only. There is no runnable application, no CLI, no backend, no frontend, no tests, no package manifests, and no source directories yet. The repo currently functions as a project specification and bootstrap design document.

The intended deliverable is not just a paper. The docs describe a real software system: a local research workspace with a frontend, backend API, reusable Python analysis modules, CLI, SQLite database, and published JSON experiment outputs.

## 2. Current Repository State

Local checkout:

- Remote: `https://github.com/phenolplus/cadybara-kitchen.git`
- Branch: `main`
- Current commit at checkout time: `0b0c534`
- Current tracked files:
  - `.gitignore`
  - `README.md`
  - `PROJECT.md`
  - `DESIGN.md`
  - `LICENSE`
  - `CLA.md`

Important status note:

- No implementation exists yet.
- No `frontend/`, `backend/`, `analysis/`, `cli/`, `database/`, `tests/`, or `published/` directories exist yet.
- No `package.json`, `pyproject.toml`, `requirements.txt`, lockfile, or test config exists yet.
- The docs define the target architecture and first milestone.

Small documentation issue:

- `README.md` refers to `LICENSE.md`, but the actual license file is named `LICENSE`.
- `README.md` contains a typo: `derivstive`.

## 3. Product Intent

The project studies prompt sensitivity in AI-CAD generation. The motivating issue is that AI-CAD systems can produce outputs that are close to user intent but wrong in subtle ways:

- Incorrect dimensions
- Broken symmetry
- Missing features
- Inconsistent spacing
- Unexpected geometry additions
- Different results from prompts that appear semantically equivalent

The project is meant to answer whether model behavior is robust to prompt wording, and whether automatic prompt expansion can make CAD generation more reliable.

The long-term vision is an automatic prompt optimizer:

1. User writes a short prompt such as `Create a mounting bracket`.
2. System expands it into a more precise internal engineering specification.
3. CAD generation runs against the expanded specification.
4. Geometry validation measures whether the output satisfied intent.
5. Lessons from experiments become prompt design recommendations or optimizer rules.

## 4. Research Phases

### Phase 1: Equivalent Prompt Robustness

Goal: determine whether equivalent wording changes generated CAD geometry.

Example equivalent prompts:

```text
Create four equally spaced holes
Create four evenly distributed holes
Generate four holes with uniform spacing
```

Expected semantic meaning: identical.

Possible observed result: different geometry.

Documented mutation categories:

- Synonyms, such as `equal` to `uniform`
- Sentence restructuring
- Unit conversion, such as `120 mm` to `12 cm` or inches
- Context injection, such as adding application context
- Noise insertion, such as adding subjective wording

Expected Phase 1 deliverables:

- `seed_prompts.json`
- `mutation_engine.py`
- Prompt robustness report

### Phase 2: Prompt Expansion Sensitivity

Goal: determine which expanded prompt formulations improve CAD output quality.

Example seed prompt:

```text
Create a mounting bracket
```

Possible expanded prompts:

```text
Create a rectangular mounting bracket 100x50x4 mm with four equally spaced mounting holes.
Create a compact mounting bracket for holding a small shelf.
Create a symmetric bracket with rounded corners and four holes.
```

Documented expansion categories:

- Dimension expansion
- Functional expansion
- Constraint expansion
- Structural expansion
- Style expansion

Expected Phase 2 deliverables:

- `expansion_taxonomy.json`
- `expansion_generator.py`
- Prompt expansion quality report

### Phase 3: Understanding LLM Interpretation Behavior

Goal: explain why semantically similar prompts produce different outputs.

Documented prompt attributes to extract:

- Prompt length
- Token count
- Constraint count
- Dimension count
- Feature count
- Adjective count
- Ordering
- Units

Expected outputs:

- Correlation analysis
- Recommended prompt structure
- Prompt design guide

## 5. Required MVP Architecture

The bootstrap architecture in `DESIGN.md` is:

```text
Frontend UI
  -> Backend API / Experiment Runner
  -> Python Analysis Modules
  -> SQLite Database
  -> Published Experiment Files
```

External LLM and CAD systems are intentionally abstracted in the MVP.

### Frontend

Suggested implementation: React + TypeScript.

Minimum pages:

- `/experiments`
- `/experiment/:id`
- `/published`

Responsibilities:

- List experiments
- Create experiments
- Inspect seed prompts
- Inspect generated prompt variants
- View results
- Publish experiment outputs

### Backend

Suggested implementation: FastAPI.

Responsibilities:

- Experiment CRUD
- Prompt generation
- Experiment execution
- Database access
- Invoke analysis modules
- Publish experiment results

Minimum documented endpoints:

```text
GET  /experiments
POST /experiments
GET  /experiments/{id}
POST /experiments/{id}/generate
POST /experiments/{id}/run
GET  /experiments/{id}/results
POST /experiments/{id}/publish
```

### Analysis Modules

Purpose: reusable Python modules that can be called by both the backend and CLI.

Required module capabilities:

```python
generate_mutations(prompt: str) -> list[PromptVariant]
generate_expansions(prompt: str) -> list[PromptVariant]
score_result(expected, actual) -> dict
generate_report(experiment_id) -> dict
```

Important constraint:

- Analysis modules must not depend on the frontend.

### CLI

Suggested implementation: Typer.

Documented example commands:

```bash
prompt-cli create-experiment
prompt-cli run EXP001
prompt-cli publish EXP001
prompt-cli report EXP001
```

The first milestone also expects:

```bash
prompt-cli generate EXP001
```

### Database

Implementation: SQLite.

Default path:

```text
workspace/research.db
```

`workspace/` is ignored by Git and intended for local generated state.

### Published Experiment Files

Purpose: stable experiment outputs that can be committed.

Expected directory:

```text
published/
```

Expected format: human-readable JSON.

Example outputs:

```text
published/robustness_hole_patterns.json
published/bracket_expansion_study.json
published/bracket_expansion.json
```

## 6. Data Model

The design document defines five core entities.

### Experiment

Represents a research study.

Fields:

- `id`
- `name`
- `description`
- `type`
- `status`
- `created_at`
- `updated_at`

### Prompt

Represents a seed prompt.

Fields:

- `id`
- `text`
- `category`
- `metadata`

### PromptVariant

Represents a mutation or expansion.

Fields:

- `id`
- `parent_prompt_id`
- `experiment_id`
- `variant_type`
- `text`
- `attributes`

Variant type examples:

- `synonym`
- `reordered`
- `unit_conversion`
- `expansion_dimension`
- `expansion_constraint`

### Run

Represents one execution of a prompt variant.

Fields:

- `id`
- `experiment_id`
- `prompt_variant_id`
- `status`
- `started_at`
- `finished_at`

### Result

Stores output and metrics from a run.

Fields:

- `id`
- `run_id`
- `metrics`
- `raw_output`

The documented SQLite schema stores JSON-like fields as text.

## 7. Quality and Evaluation Requirements

The docs do not define a formal human qualitative rubric. They mostly describe metric-based evaluation.

Documented geometry metrics:

- Volume
- Bounding dimensions
- Surface area

Documented constraint checks:

- Hole count
- Spacing
- Symmetry
- Dimensions

Documented feature checks:

- Fillets
- Ribs
- Patterns

Documented expansion quality dimensions:

- Accuracy, especially dimensions
- Constraint satisfaction, especially spacing, symmetry, and feature count
- Unexpected geometry, such as extra ribs, unexpected fillets, or missing holes

Example score shape:

```json
{
  "dimension_score": 0.95,
  "constraint_score": 0.83,
  "overall": 0.90
}
```

Recommended MVP interpretation:

- Build a scoring interface now, but use deterministic mock or structured output initially.
- Do not block the MVP on real CAD geometry parsing unless the senior lead chooses a specific CAD output format.
- Keep scoring modular so real CAD analyzers can be added later.

## 8. Credits, External Services, and AI-CAD Integrations

The docs do not say where to get credits from.

There is no mention of:

- API keys
- Provider accounts
- Model credits
- CAD service credits
- Cloud billing
- Funding
- Token budgets

`DESIGN.md` explicitly says external systems, including LLMs and CAD generation systems, are intentionally abstracted. The bootstrap scope also says the MVP must not include external services.

Recommended MVP approach:

- Implement provider interfaces or adapters.
- Include a deterministic local fake generator for development and testing.
- Make real LLM or CAD integrations optional future plugins.
- Keep API keys out of the repo and document `.env` usage only when real providers are introduced.

## 9. AI-Generated Code Policy

The repo does not explicitly forbid AI-generated code.

However, `CLA.md` requires contributors to represent that they have sufficient rights to submit their contributions. It defines contributions broadly, including source code, docs, designs, specs, test materials, patches, and comments.

Practical interpretation:

- AI-assisted code is not banned by the current docs.
- Contributors still need to be comfortable making the CLA representations.
- If this is an organizational concern, add a short `CONTRIBUTING.md` section clarifying whether AI-assisted code is allowed and under what conditions.

## 10. License and Contribution Constraints

License:

- GPLv3, from the root `LICENSE` file.

Contribution agreement:

- `CLA.md` contains a contributor copyright assignment and patent license agreement.
- Contributions are submitted under broad assignment terms.
- Patent ownership is retained by contributors, but a broad patent license is granted to the project and downstream users for patent rights arising from contributions.

Engineering impact:

- Dependencies should be chosen with GPLv3 compatibility in mind.
- If the project is intended to be used inside proprietary systems, GPLv3 implications should be reviewed before implementation decisions harden.
- The senior lead should confirm whether the CLA text is intentional before soliciting external contributions.

## 11. First Working Milestone

The design document defines success as a user being able to:

1. Run:

```bash
prompt-cli create-experiment
```

2. Run:

```bash
prompt-cli generate EXP001
```

3. Run:

```bash
prompt-cli run EXP001
```

4. Open the UI:

```text
localhost:3000
```

5. View:

- Prompt variants
- Results
- Metrics

6. Run:

```bash
prompt-cli publish EXP001
```

7. Produce:

```text
published/bracket_expansion.json
```

This is the minimum viable implementation described by the current docs.

## 12. Recommended Implementation Plan

### Step 1: Establish Project Skeleton

Create documented directories:

```text
frontend/
backend/
analysis/
cli/
database/
published/
scripts/
tests/
```

Add Python packaging, likely `pyproject.toml`, with dependencies for:

- FastAPI
- Uvicorn
- Typer
- Pydantic
- SQLAlchemy or direct SQLite access
- Pytest

Add frontend tooling, likely Vite + React + TypeScript.

### Step 2: Define Shared Python Models

Create Pydantic models for:

- Experiment
- Prompt
- PromptVariant
- Run
- Result
- PublishedExperiment

Keep them reusable across backend, CLI, and analysis modules.

### Step 3: Implement SQLite Layer

Implement the schema from `DESIGN.md`.

Use a local database path:

```text
workspace/research.db
```

Add initialization command or automatic bootstrap.

### Step 4: Implement Analysis MVP

Start with deterministic local logic:

- Seed prompt loading
- Rule-based mutations
- Rule-based expansions
- Mock execution result generation
- Basic scoring
- Report generation

This allows the entire workflow to function without external credits or CAD systems.

### Step 5: Implement CLI

Implement:

```bash
prompt-cli create-experiment
prompt-cli generate EXP001
prompt-cli run EXP001
prompt-cli report EXP001
prompt-cli publish EXP001
```

The CLI should use the same services as the backend.

### Step 6: Implement Backend API

Expose the documented endpoints.

Use the same database and analysis services as the CLI.

### Step 7: Implement Frontend

Build a research workspace, not a marketing page.

Minimum views:

- Experiment list
- Experiment detail
- Prompt variants table
- Run results table
- Metrics summary
- Published experiments view

### Step 8: Publish JSON Output

Implement `publish` so experiment outputs become stable JSON under `published/`.

This should include:

- Experiment metadata
- Seed prompts
- Variants
- Results
- Metrics
- Summary statistics
- Conclusions or recommendations

## 13. Testing Strategy

Because no tests exist yet, the senior lead should expect to define the baseline test structure.

Recommended tests:

- Unit tests for mutation generation
- Unit tests for expansion generation
- Unit tests for scoring
- Unit tests for report generation
- SQLite repository tests using a temporary database
- CLI integration tests using Typer's test runner
- FastAPI endpoint tests using `TestClient`
- Frontend smoke tests for the three required pages
- Golden-file or schema tests for published JSON output

Minimum acceptance test for MVP:

1. Create an experiment.
2. Generate prompt variants.
3. Run the experiment with a fake local executor.
4. Persist results to SQLite.
5. View results through API and UI.
6. Publish a JSON file.
7. Validate the JSON schema.

## 14. Major Open Decisions

These are not specified in the current docs and need senior-level decisions.

### CAD Output Format

The docs mention CAD outputs and geometry metrics but do not specify file formats.

Options might include:

- STEP
- STL
- OBJ
- OpenSCAD
- CADQuery Python objects
- Structured mock JSON for MVP

Recommendation: use structured mock JSON for the first milestone, then introduce real CAD formats once an integration target is chosen.

### CAD Generator Interface

The docs abstract external CAD generation systems.

Need to decide:

- What adapter interface should a CAD generator implement?
- Is generation synchronous or asynchronous?
- What does `raw_output` contain?
- How are failures represented?

### Scoring Truth Model

The docs say to compare expected versus actual outputs, but they do not define how expected geometry is represented.

Need to decide:

- Is expected intent encoded manually in seed prompt metadata?
- Is expected intent extracted from prompts?
- Do tests use human-labeled expected values?
- How are ambiguous prompts scored?

### Prompt Dataset Scope

`PROJECT.md` suggests 50 to 100 seed prompts.

Need to decide:

- Which CAD domains are in scope first?
- How much complexity is allowed in the seed set?
- How should prompts encode expected dimensions and constraints?

### Prompt Expansion Source

Docs allow both rule-based and LLM-based expansion.

Need to decide:

- Is MVP rule-only?
- If LLM-based expansion is added later, which provider is used?
- How are prompts and outputs cached for reproducibility?

### Frontend Depth

Docs define pages but not UX details.

Need to decide:

- Is the UI read-only for MVP except experiment creation?
- Should users edit prompts manually?
- Should users compare variants side by side?
- Should results include charts in MVP?

## 15. What Is Explicitly Out of Scope for Bootstrap

The design document says the bootstrap version must not include:

- Distributed systems
- Authentication
- Cloud storage
- Queues
- External services
- Production deployment concerns

This means the first implementation should stay local, simple, and reproducible.

## 16. Suggested Senior Lead Framing

This should be treated as an MVP research platform.

The immediate engineering target is not "solve AI-CAD quality." It is:

- Create a local experiment workflow.
- Generate prompt variants.
- Run deterministic placeholder experiments.
- Store and display results.
- Publish reproducible JSON.
- Leave clean extension points for real LLM and CAD systems.

Once the skeleton is working, the project can evolve into a real research pipeline by replacing mock generation and simple scoring with actual CAD generation, geometry parsing, and statistical analysis.

