from __future__ import annotations

import json
from pathlib import Path

import pytest

from cadybara_cad_diffusion import (
    CadDiffusionRecord,
    CadProgram,
    ExtrudeOp,
    cad_grammar_allowed_next,
    eval_cad_diffusion_run,
    latest_checkpoint,
    load_prepared_examples,
    normalized_edit_distance,
    prepare_fusion360_dataset,
    program_metrics,
    program_to_cadquery_code,
    program_to_tokens,
    tokens_to_program,
    train_diffusion_model,
    validate_cad_token_grammar,
)


def test_cad_tokens_round_trip_and_compile_to_cadquery() -> None:
    program = CadProgram(
        ops=[
            ExtrudeOp(profile="rect", mode="new", width=40, height=20, distance=8),
            ExtrudeOp(profile="circle", mode="cut", x=10, y=0, radius=5, distance=8),
        ]
    )

    tokens = program_to_tokens(program)
    parsed = tokens_to_program(tokens)
    code = program_to_cadquery_code(parsed)
    metrics = program_metrics(parsed)

    assert tokens[0] == "<BOS>"
    assert tokens[-1] == "<EOS>"
    assert parsed.ops[0].profile == "rect"
    assert parsed.ops[1].mode == "cut"
    assert 'cq.Workplane("XY")' in code
    assert ".cut(op_1)" in code
    assert metrics["operation_count"] == 2
    assert normalized_edit_distance(tokens, tokens) == 0.0


def test_cad_token_grammar_accepts_valid_program_and_rejects_bad_sequences() -> None:
    program = CadProgram(
        ops=[
            ExtrudeOp(profile="rect", mode="new", width=40, height=15, distance=5),
            ExtrudeOp(profile="circle", mode="cut", x=10, y=0, radius=5, distance=5),
        ]
    )
    tokens = program_to_tokens(program)

    validate_cad_token_grammar(tokens)
    assert cad_grammar_allowed_next([]) == {"<BOS>"}
    assert cad_grammar_allowed_next(["<BOS>"]) == {"OP:EXTRUDE"}

    first_cut = [
        "<BOS>",
        "OP:EXTRUDE",
        "PROFILE:CIRCLE",
        "MODE:CUT",
        "X:+000",
        "Y:+000",
        "R:005",
        "D:005",
        "ENDOP",
        "<EOS>",
    ]
    with pytest.raises(ValueError, match="MODE:JOIN|MODE:NEW"):
        validate_cad_token_grammar(first_cut)

    malformed_overnight_prefix = [
        "<BOS>",
        "OP:EXTRUDE",
        "PROFILE:RECT",
        "MODE:NEW",
        "X:+000",
        "Y:+000",
        "W:040",
        "H:015",
        "ENDOP",
    ]
    with pytest.raises(ValueError, match="expected D token"):
        validate_cad_token_grammar(malformed_overnight_prefix)


def test_prepare_fusion360_dataset_filters_unsupported_examples(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "fusion"
    train_dir = dataset_dir / "train"
    train_dir.mkdir(parents=True)
    (train_dir / "supported.json").write_text(
        """
{
  "ops": [
    {"op": "extrude", "profile": "rect", "mode": "new", "width": 30, "height": 20, "distance": 10}
  ]
}
""".strip(),
        encoding="utf-8",
    )
    (train_dir / "unsupported.json").write_text(
        """
{
  "ops": [
    {"op": "extrude", "profile": "spline", "distance": 10}
  ]
}
""".strip(),
        encoding="utf-8",
    )

    output_dir = tmp_path / "prepared"
    manifest = prepare_fusion360_dataset(dataset_dir, output_dir, max_len=64)
    examples = load_prepared_examples(output_dir, split="train")

    assert manifest.scanned_json == 2
    assert manifest.written == 1
    assert manifest.unsupported == 1
    assert examples[0].example_id == "supported"
    assert (output_dir / "unsupported.jsonl").exists()


def test_prepare_reads_fusion_profile_units_and_train_test_split(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "fusion"
    dataset_dir.mkdir()
    (dataset_dir / "train_test.json").write_text(
        '{"test": ["fusion_rect"], "train": []}',
        encoding="utf-8",
    )
    (dataset_dir / "fusion_rect.json").write_text(
        """
{
  "timeline": [
    {"index": 0, "entity": "sketch1"},
    {"index": 1, "entity": "extrude1"}
  ],
  "entities": {
    "sketch1": {
      "name": "Sketch1",
      "type": "Sketch",
      "profiles": {
        "profile1": {
          "loops": [
            {
              "is_outer": true,
              "profile_curves": [
                {"type": "Line3D", "start_point": {"x": 0, "y": 0}, "end_point": {"x": 2, "y": 0}},
                {"type": "Line3D", "start_point": {"x": 2, "y": 0}, "end_point": {"x": 2, "y": 1}},
                {"type": "Line3D", "start_point": {"x": 2, "y": 1}, "end_point": {"x": 0, "y": 1}},
                {"type": "Line3D", "start_point": {"x": 0, "y": 1}, "end_point": {"x": 0, "y": 0}}
              ]
            }
          ]
        }
      }
    },
    "extrude1": {
      "name": "Extrude1",
      "type": "ExtrudeFeature",
      "profiles": [{"sketch": "sketch1", "profile": "profile1"}],
      "operation": "NewBodyFeatureOperation",
      "extent_one": {"distance": {"value": 1.5}}
    }
  }
}
""".strip(),
        encoding="utf-8",
    )

    output_dir = tmp_path / "prepared"
    manifest = prepare_fusion360_dataset(dataset_dir, output_dir, max_len=64)
    examples = load_prepared_examples(output_dir, split="test")

    assert manifest.written == 1
    assert examples[0].split == "test"
    op = examples[0].program.ops[0]
    assert op.width == 20
    assert op.height == 10
    assert op.distance == 15


def test_cad_diffusion_eval_summarizes_append_only_records(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    records = [
        CadDiffusionRecord(
            sample_id="a",
            experiment_id="run",
            timestamp_utc="2026-05-28T00:00:00Z",
            checkpoint_path="checkpoint.pt",
            seed=1,
            tokens=["<BOS>", "OP:EXTRUDE", "<EOS>"],
            program={"units": "mm", "ops": []},
            parse_error=None,
            compile_error=None,
            render_error=None,
            artifacts={"stl": "model.stl"},
            metrics={"operation_count": 1},
            nearest_neighbor_distance=0.25,
            elapsed_ms=10,
        ),
        CadDiffusionRecord(
            sample_id="b",
            experiment_id="run",
            timestamp_utc="2026-05-28T00:00:01Z",
            checkpoint_path="checkpoint.pt",
            seed=2,
            tokens=["<BOS>", "<MASK>", "<EOS>"],
            program=None,
            parse_error="bad tokens",
            compile_error=None,
            render_error=None,
            artifacts={},
            metrics={},
            nearest_neighbor_distance=None,
            elapsed_ms=10,
        ),
    ]
    with (run_dir / "results.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(record.model_dump_json() + "\n")

    summary = eval_cad_diffusion_run(run_dir)

    assert summary.total == 2
    assert summary.parse_valid == 1
    assert summary.compiled == 1
    assert summary.renderable == 1
    assert summary.unique_token_sequences == 2
    assert summary.mean_nearest_neighbor_distance == 0.25


def test_train_stop_callback_saves_final_checkpoint(tmp_path: Path) -> None:
    pytest.importorskip("torch")
    data_dir = tmp_path / "tokens"
    data_dir.mkdir()
    program = CadProgram(ops=[ExtrudeOp(profile="rect", mode="new", width=20, height=10, distance=5)])
    tokens = program_to_tokens(program, max_len=32)
    example = {
        "example_id": "tiny",
        "split": "train",
        "source_path": "tiny.json",
        "program": program.model_dump(mode="json"),
        "tokens": tokens,
        "token_count": len(tokens),
    }
    (data_dir / "train.jsonl").write_text(json.dumps(example) + "\n", encoding="utf-8")
    output_dir = tmp_path / "model"
    steps_seen: list[int] = []

    def on_progress(progress: dict) -> None:
        if progress.get("phase") == "training":
            steps_seen.append(int(progress["step"]))

    summary = train_diffusion_model(
        data_dir,
        output_dir,
        max_steps=5,
        batch_size=1,
        max_len=32,
        d_model=32,
        layers=1,
        heads=4,
        checkpoint_interval=100,
        time_limit_minutes=1,
        seed=7,
        resume=False,
        should_stop=lambda: bool(steps_seen),
        on_progress=on_progress,
    )

    assert summary.steps == 1
    assert summary.checkpoint_path.exists()
    assert latest_checkpoint(output_dir) == summary.checkpoint_path
