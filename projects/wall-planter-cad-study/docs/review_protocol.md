# Review Protocol

Review the generated product, not the prose quality.

## What To Score

Use a 1-10 score:

- 1: no usable CAD product, irrelevant geometry, or impossible to inspect
- 3: some object exists but misses the core wall-planter intent
- 5: recognizable planter but major missing features or poor printability
- 7: mostly correct product with minor missing or malformed details
- 9: strong product that satisfies almost all stated requirements
- 10: excellent product, printable, coherent, and faithful to the prompt

Keyboard scoring in the lab:

- `1` through `9` record scores 1-9
- `0` records 10
- Left/right arrows move between products

## Score The Same Way Across Prompt Levels

For low-detail prompts, judge whether the product reasonably satisfies the
limited prompt. Do not punish prompt 1 for missing dimensions it never asked
for. For high-detail prompts, judge adherence to the explicit dimensions,
holes, keyhole slot, flat back panel, fillets, and support-free printability.

## Keep These Notes In Mind

Rendering failure is itself useful data. If the generated code cannot become a
viewable STL/STEP, score the product low even if the code looks plausible.

Do not score based on model name expectations. Score only the product you see.

