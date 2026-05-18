# Prompt Robustness and Prompt Expansion Research Framework
## Goal: Understanding How Prompt Formulation Affects AI CAD Model Quality

## Overview

AI CAD systems frequently generate models that are *close* to user intent but contain subtle errors:

- Incorrect dimensions
- Broken symmetry
- Missing features
- Inconsistent spacing
- Unexpected geometry additions
- Different results from seemingly equivalent prompts

The underlying issue may not only be CAD generation itself, but also how language is interpreted.

This project investigates two related questions:

### Phase 1 — Equivalent Prompt Robustness

Study whether different ways of expressing the same intent produce equivalent CAD outputs.

Question:

> Does the system understand design intent, or does it rely on specific wording patterns?

Example:

```text
Create four equally spaced holes

Create four evenly distributed holes

Generate four holes with uniform spacing
```

Expected meaning:

```text
Identical
```

Potential result:

```text
Different geometry generated
```

---

### Phase 2 — Prompt Expansion Sensitivity

Study how expanding a short prompt into multiple plausible detailed specifications affects output quality.

Question:

> Which expanded representations best communicate design intent?

Example:

Starting prompt:

```text
Create a mounting bracket
```

Possible expansions:

```text
Expansion A

Create a rectangular mounting bracket
100×50×4 mm with four equally
spaced mounting holes.
```

```text
Expansion B

Create a compact mounting bracket
for holding a small shelf.
```

```text
Expansion C

Create a symmetric bracket with
rounded corners and four holes.
```

Expected meaning:

```text
Similar intent
```

Potential result:

```text
Large quality differences
```

---

## Research Questions

### Prompt robustness questions

- Does synonym replacement affect geometry?
- Does sentence ordering matter?
- Does wording complexity matter?
- Does unit representation matter?
- Does added context affect behavior?

---

### Prompt expansion questions

- Does additional detail improve quality?
- Which types of details matter most?
- Is there an optimal prompt length?
- Which expanded prompts produce stable outputs?
- Which prompt structures align with LLM understanding?

---

## High-Level Architecture

```text
Seed Prompt
      ↓

Phase 1:
Equivalent Prompt Generation
      ↓

Phase 2:
Prompt Expansion Generation
      ↓

CAD Generation System
      ↓

Geometry Analysis
      ↓

Quality Metrics
      ↓

Sensitivity Analysis
      ↓

Reports + Recommendations
```

---

# Phase 1: Equivalent Prompt Robustness Study

## Goal

Evaluate whether equivalent wording changes generated geometry.

---

## Work Item 1: Build Seed Prompt Dataset

Create approximately:

```text
50–100 prompts
```

Examples:

```text
Create a mounting plate

Create a gear with 20 teeth

Create a rectangular enclosure

Create a pulley

Create a bracket with holes
```

Requirements:

- Dimensions
- Constraints
- Mechanical features
- Multiple complexity levels

Deliverable:

```text
seed_prompts.json
```

---

## Work Item 2: Prompt Mutation Engine

Generate alternate forms while preserving meaning.

Mutation categories:

### Synonyms

```text
equal → uniform
create → generate
```

---

### Sentence restructuring

```text
Create four holes on a plate

↓

On a plate, create four holes
```

---

### Unit conversion

```text
120 mm

↓

12 cm

↓

4.724 inches
```

---

### Context injection

```text
Create a bracket

↓

Create a bracket suitable for
electronics applications
```

---

### Noise insertion

```text
Please create a mounting plate
that looks practical and modern
```

---

Deliverable:

```text
mutation_engine.py
```

---

## Work Item 3: Robustness Scoring

Measure:

### Geometry

```text
Volume
Bounding dimensions
Surface area
```

---

### Constraints

```text
Hole count
Spacing
Symmetry
Dimensions
```

---

### Features

```text
Fillets
Ribs
Patterns
```

---

Example:

```text
Original prompt:
Quality score: 92

Synonym variant:
Quality score: 88

Unit variant:
Quality score: 70
```

---

## Phase 1 Milestone

Output:

```text
Prompt robustness report

Hole pattern prompts:

Synonym sensitivity:
Low

Unit sensitivity:
High

Ordering sensitivity:
Medium
```

---

# Phase 2: Prompt Expansion Sensitivity Study

## Goal

Determine which expanded prompt formulations improve CAD quality.

---

## Work Item 4: Expansion Taxonomy

Define expansion categories.

---

### Dimension expansion

```text
Create bracket

↓

Create bracket
100×50×4 mm
```

---

### Functional expansion

```text
Create bracket

↓

Create bracket suitable for
holding shelves
```

---

### Constraint expansion

```text
Create bracket

↓

Create symmetric bracket
with equally spaced holes
```

---

### Structural expansion

```text
Create bracket

↓

Create bracket with ribs
and rounded corners
```

---

### Style expansion

```text
Create bracket

↓

Create lightweight industrial
bracket
```

---

Deliverable:

```text
expansion_taxonomy.json
```

---

## Work Item 5: Expansion Generator

Generate:

```text
20–50 expanded prompts
per seed prompt
```

Methods:

### Rule-based expansion

```text
Add dimensions

Add constraints

Add structure
```

---

### LLM-based expansion

Example instruction:

```text
Generate ten plausible
expanded engineering specifications
for this CAD request.
```

---

Deliverable:

```text
expansion_generator.py
```

---

## Work Item 6: Expansion Quality Analysis

Compare generated outputs.

Example:

Seed prompt:

```text
Create mounting bracket
```

Results:

```text
Expansion A:
Quality score = 95

Expansion B:
Quality score = 74

Expansion C:
Quality score = 58
```

---

Measure:

### Accuracy

```text
Dimensions correct
```

---

### Constraint satisfaction

```text
Spacing
Symmetry
Feature count
```

---

### Unexpected geometry

```text
Extra ribs

Unexpected fillets

Missing holes
```

---

## Phase 2 Milestone

Output:

```text
Prompt expansion quality report
```

Example:

```text
Dimensions:
+24%

Symmetry constraints:
+16%

Functional descriptions:
+5%

Style wording:
−9%
```

---

# Phase 3: Understanding LLM Interpretation Behavior

## Goal

Understand how language changes influence internal model interpretation.

This phase attempts to answer:

> Why did two equivalent prompts produce different CAD outputs?

---

## Work Item 7: Prompt Attribute Extraction

Measure prompt characteristics:

```text
Prompt length

Token count

Constraint count

Dimension count

Feature count

Adjective count

Ordering

Units
```

---

## Work Item 8: Correlation Analysis

Example findings:

```text
Positive contributors:

Explicit dimensions
Symmetry constraints
Feature ordering

Negative contributors:

Long prompts (>80 words)

Mixed units

Stylistic adjectives
```

---

## Work Item 9: Discover Optimal Prompt Structure

Possible output:

```text
Recommended internal prompt structure:

1. Dimensions

2. Constraints

3. Features

4. Functional description

5. Style information
```

---

# Final Deliverables

## Dataset

```text
Seed prompt

Equivalent prompts

Expanded prompts

Generated CAD outputs

Quality metrics
```

---

## Robustness Reports

Example:

```text
Equivalent prompt sensitivity:

Synonyms:
Low impact

Sentence ordering:
Moderate impact

Units:
High impact
```

---

## Expansion Reports

Example:

```text
Dimensions:
+23%

Constraint details:
+18%

Long prompts:
−12%

Industrial style wording:
−8%
```

---

## Recommended Prompt Design Guide

Example:

```text
Recommended format:

Dimensions
↓
Constraints
↓
Features
↓
Functional description
↓
Style details
```

---

# Long-Term Vision

```text
User Prompt
      ↓

Automatic Prompt Optimizer

      ↓

Expanded Internal Specification

      ↓

CAD Generation

      ↓

Geometry Validation
```

The eventual goal is not simply to measure prompt quality.

The larger goal is to allow users to write:

```text
Create a mounting bracket
```

while the system automatically learns:

```text
The CAD model is more accurate if
the internal representation becomes:

100×50×4 mm
Symmetric
Four equally spaced holes
Rounded corners
```

This potentially turns prompt research into a future component of the AI CAD generation pipeline itself.