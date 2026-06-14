from __future__ import annotations

import json
from pathlib import Path

import pytest

from cadybara_cad_diffusion import (
    eval_voxel_diffusion_run,
    export_voxel_artifacts,
    latest_voxel_checkpoint,
    load_voxel_examples,
    prepare_voxel_dataset,
    sample_voxel_diffusion_model,
    train_voxel_diffusion_model,
    voxel_discriminator_metrics,
)


pytest.importorskip("numpy")
pytest.importorskip("trimesh")
pytest.importorskip("skimage")


def write_cube_obj(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "v -1 -1 -1",
                "v 1 -1 -1",
                "v 1 1 -1",
                "v -1 1 -1",
                "v -1 -1 1",
                "v 1 -1 1",
                "v 1 1 1",
                "v -1 1 1",
                "f 1 2 3",
                "f 1 3 4",
                "f 5 8 7",
                "f 5 7 6",
                "f 1 5 6",
                "f 1 6 2",
                "f 2 6 7",
                "f 2 7 3",
                "f 3 7 8",
                "f 3 8 4",
                "f 4 8 5",
                "f 4 5 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_prepare_voxel_dataset_records_success_and_failure(tmp_path: Path) -> None:
    source_dir = tmp_path / "reconstruction"
    source_dir.mkdir()
    write_cube_obj(source_dir / "cube.obj")
    (source_dir / "bad.obj").write_text("not an obj\n", encoding="utf-8")
    (tmp_path / "train_test.json").write_text(json.dumps({"test": ["cube"], "train": []}), encoding="utf-8")

    output_dir = tmp_path / "voxels"
    manifest = prepare_voxel_dataset(source_dir, output_dir, resolution=32)
    examples = load_voxel_examples(output_dir, split="test")

    assert manifest.scanned_obj == 2
    assert manifest.written == 1
    assert manifest.failed == 1
    assert examples[0].example_id == "cube"
    assert examples[0].resolution == 32
    assert examples[0].filled_voxels > 0
    assert (output_dir / "failures.jsonl").exists()


def test_voxel_grid_exports_stl_and_metrics(tmp_path: Path) -> None:
    np = pytest.importorskip("numpy")
    voxels = np.zeros((32, 32, 32), dtype=bool)
    voxels[8:24, 8:24, 8:24] = True

    artifacts, metrics, export_error = export_voxel_artifacts(voxels, tmp_path)

    assert export_error is None
    assert Path(artifacts["stl"]).exists()
    assert Path(artifacts["voxels"]).exists()
    assert Path(artifacts["preview_png"]).exists()
    assert metrics["occupancy_ratio"] > 0
    assert metrics["renderable"] is True
    assert voxel_discriminator_metrics(voxels)["filled_voxels"] > 0


def test_voxel_train_stop_callback_saves_checkpoint(tmp_path: Path) -> None:
    pytest.importorskip("torch")
    source_dir = tmp_path / "reconstruction"
    source_dir.mkdir()
    write_cube_obj(source_dir / "cube.obj")
    data_dir = tmp_path / "voxels"
    prepare_voxel_dataset(source_dir, data_dir, resolution=32)
    output_dir = tmp_path / "model"
    steps_seen: list[int] = []

    def on_progress(progress: dict) -> None:
        if progress.get("phase") == "training":
            steps_seen.append(int(progress["step"]))

    summary = train_voxel_diffusion_model(
        data_dir,
        output_dir,
        resolution=32,
        max_steps=2,
        batch_size=1,
        base_channels=4,
        timesteps=10,
        checkpoint_interval=100,
        time_limit_minutes=1,
        seed=7,
        resume=False,
        should_stop=lambda: bool(steps_seen),
        on_progress=on_progress,
    )

    assert summary.steps == 1
    assert summary.checkpoint_path.exists()
    assert latest_voxel_checkpoint(output_dir) == summary.checkpoint_path


def test_voxel_sample_and_eval_records_artifacts(tmp_path: Path) -> None:
    pytest.importorskip("torch")
    source_dir = tmp_path / "reconstruction"
    source_dir.mkdir()
    write_cube_obj(source_dir / "cube.obj")
    data_dir = tmp_path / "voxels"
    prepare_voxel_dataset(source_dir, data_dir, resolution=32)
    model_dir = tmp_path / "model"
    train_voxel_diffusion_model(
        data_dir,
        model_dir,
        resolution=32,
        max_steps=1,
        batch_size=1,
        base_channels=4,
        timesteps=10,
        checkpoint_interval=1,
        time_limit_minutes=1,
        seed=8,
        resume=False,
    )
    checkpoint = latest_voxel_checkpoint(model_dir)
    assert checkpoint is not None
    run_dir = tmp_path / "run"

    records = sample_voxel_diffusion_model(
        checkpoint,
        run_dir,
        count=1,
        sample_steps=2,
        threshold=0.5,
        seed=9,
        data_dir=data_dir,
    )
    summary = eval_voxel_diffusion_run(run_dir)

    assert len(records) == 1
    assert Path(records[0].artifacts["voxels"]).exists()
    assert "occupancy_ratio" in records[0].metrics
    assert summary.total == 1
