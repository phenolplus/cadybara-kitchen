# Design: Prompt Robustness and Prompt Expansion Research Framework (Bootstrap Version)

Version: 0.1  
Status: Bootstrap / MVP  
Target audience: Coding agents and developers  
Goal: Define the minimum architecture necessary to begin prompt robustness and prompt expansion experiments.

---

# 1. Purpose

This project researches how prompt wording and prompt expansion affect AI-CAD model quality.

The system investigates two major questions:

1. Equivalent Prompt Robustness

```text
Create four equally spaced holes

vs

Generate four uniformly distributed holes
```

Do equivalent prompts generate equivalent CAD outputs?

---

2. Prompt Expansion Sensitivity

```text
Create mounting bracket
```

↓

```text
Create a 100x50x4 mm symmetric bracket
with four equally spaced holes.
```

Which expanded forms improve generated quality?

---

This bootstrap version focuses on creating:

- prompt datasets
- prompt mutation generation
- experiment execution
- result storage
- analysis modules
- visualization workspace

External systems (LLMs, CAD generation systems) are intentionally abstracted.

---

# 2. High-Level Architecture

```text
Frontend UI
    ↓

Backend API / Experiment Runner
    ↓

Python Analysis Modules
    ↓

SQLite Database
    ↓

Published Experiment Files
```

---

# 3. Components

## Frontend

Purpose:

Research workspace UI.

Responsibilities:

- list experiments
- create experiments
- inspect prompts
- inspect generated variants
- view results
- publish experiment outputs

Suggested implementation:

```text
React + TypeScript
```

Minimum pages:

```text
/experiments

/experiment/:id

/published
```

---

## Backend

Purpose:

Experiment orchestration and API layer.

Responsibilities:

- experiment CRUD
- prompt generation
- experiment execution
- database access
- invoke analysis modules
- publish experiment results

Suggested implementation:

```text
FastAPI
```

---

## Analysis Modules

Purpose:

Reusable Python modules for analysis and calculations.

Must support:

1. Backend use

```python
from analysis.metrics import score
```

2. CLI use

```bash
prompt-analysis score experiment_001
```

Responsibilities:

- prompt mutations
- prompt expansion
- scoring
- statistics
- reporting

Must NOT depend on frontend.

---

## CLI Wrapper

Purpose:

Provide command line access to analysis modules and database operations.

Suggested implementation:

```text
Typer
```

Examples:

```bash
prompt-cli create-experiment

prompt-cli run EXP001

prompt-cli publish EXP001

prompt-cli report EXP001
```

---

## Database

Purpose:

Store active experiment state.

Implementation:

```text
SQLite
```

Default path:

```text
workspace/research.db
```

Notes:

- local only
- no distributed behavior required
- no ORM requirement
- SQLAlchemy acceptable

---

## Published Experiment Data

Purpose:

Store useful experiment outputs permanently.

Requirements:

- checked into source control
- human-readable
- stable format
- independent of SQLite DB

Suggested format:

```text
JSON
```

Directory:

```text
published/
```

Example:

```text
published/

    robustness_hole_patterns.json

    bracket_expansion_study.json
```

---

# 4. Repository Structure

```text
./

├── frontend/

├── backend/

├── analysis/

│   ├── mutation/
│   │
│   ├── expansion/
│   │
│   ├── metrics/
│   │
│   ├── scoring/
│   │
│   └── reporting/

├── cli/

├── database/

├── workspace/
│
│   ├── research.db
│   │
│   ├── generated/
│   │
│   ├── reports/
│   │
│   └── artifacts/

├── published/

├── scripts/

└── tests/
```

---

# 5. Core Data Model

---

## Experiment

Represents a research study.

Fields:

```text
id

name

description

type

status

created_at

updated_at
```

Example:

```json
{
    "id":"EXP001",
    "name":"Bracket Expansion Study",
    "type":"expansion",
    "status":"running"
}
```

---

## Prompt

Represents seed prompt.

Fields:

```text
id

text

category

metadata
```

Example:

```json
{
    "id":"P001",
    "text":"Create mounting bracket",
    "category":"mechanical"
}
```

---

## PromptVariant

Represents generated mutation or expansion.

Fields:

```text
id

parent_prompt_id

experiment_id

variant_type

text

attributes
```

variant_type examples:

```text
synonym

reordered

unit_conversion

expansion_dimension

expansion_constraint
```

Example:

```json
{
    "id":"V001",
    "parent_prompt_id":"P001",
    "variant_type":"synonym",
    "text":"Generate mounting bracket"
}
```

---

## Run

Represents a single execution.

Fields:

```text
id

experiment_id

prompt_variant_id

status

started_at

finished_at
```

---

## Result

Stores experiment output.

Fields:

```text
id

run_id

metrics

raw_output
```

Example:

```json
{
    "metrics":{
        "dimension_score":0.92,
        "constraint_score":0.81,
        "overall":0.88
    }
}
```

---

# 6. SQLite Schema

Minimum schema:

```sql
CREATE TABLE experiments (

    id TEXT PRIMARY KEY,

    name TEXT,

    description TEXT,

    type TEXT,

    status TEXT,

    created_at TEXT,

    updated_at TEXT
);

CREATE TABLE prompts (

    id TEXT PRIMARY KEY,

    text TEXT,

    category TEXT,

    metadata TEXT
);

CREATE TABLE prompt_variants (

    id TEXT PRIMARY KEY,

    parent_prompt_id TEXT,

    experiment_id TEXT,

    variant_type TEXT,

    text TEXT,

    attributes TEXT
);

CREATE TABLE runs (

    id TEXT PRIMARY KEY,

    experiment_id TEXT,

    prompt_variant_id TEXT,

    status TEXT,

    started_at TEXT,

    finished_at TEXT
);

CREATE TABLE results (

    id TEXT PRIMARY KEY,

    run_id TEXT,

    metrics TEXT,

    raw_output TEXT
);
```

JSON fields stored as text.

---

# 7. Analysis Module Interfaces

Analysis modules must be importable and CLI-usable.

---

## Mutation

```python
generate_mutations(
    prompt:str
) -> list[PromptVariant]
```

---

## Expansion

```python
generate_expansions(
    prompt:str
) -> list[PromptVariant]
```

---

## Scoring

```python
score_result(
    expected,
    actual
)
```

Returns:

```python
{
    "dimension_score":0.95,
    "constraint_score":0.83,
    "overall":0.90
}
```

---

## Reporting

```python
generate_report(
    experiment_id
)
```

Returns:

```python
{
    "summary":{},
    "charts":[],
    "statistics":[]
}
```

---

# 8. Backend API

Minimum endpoints:

---

Experiments

```text
GET /experiments

POST /experiments

GET /experiments/{id}
```

---

Prompt variants

```text
POST /experiments/{id}/generate
```

Generates:

```text
mutations
expansions
```

---

Execution

```text
POST /experiments/{id}/run
```

---

Results

```text
GET /experiments/{id}/results
```

---

Publishing

```text
POST /experiments/{id}/publish
```

Writes:

```text
published/{name}.json
```

---

# 9. Published File Format

Example:

```json
{
    "experiment":"Bracket Expansion Study",

    "date":"2026-05-17",

    "seed_prompts":[...],

    "variants":[...],

    "statistics":{

        "dimension_effect":0.24,

        "constraint_effect":0.18
    },

    "conclusions":[

        "Explicit dimensions improve quality",

        "Long prompts reduce consistency"
    ]
}
```

---

# 10. Bootstrap Scope Constraints

Must include:

✓ SQLite storage

✓ backend experiment execution

✓ reusable analysis modules

✓ CLI wrapper

✓ frontend workspace

✓ published experiment files

---

Must NOT include:

✗ distributed systems

✗ authentication

✗ cloud storage

✗ queues

✗ external services

✗ production deployment concerns

---

# 11. First Working Milestone

Success condition:

User can:

1.

```bash
prompt-cli create-experiment
```

2.

```bash
prompt-cli generate EXP001
```

3.

```bash
prompt-cli run EXP001
```

4.

Open UI:

```text
localhost:3000
```

5.

View:

- prompt variants
- results
- metrics

6.

```bash
prompt-cli publish EXP001
```

Produces:

```text
published/bracket_expansion.json
```

This is considered the minimum viable implementation.