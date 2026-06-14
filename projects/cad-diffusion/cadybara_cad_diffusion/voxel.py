from __future__ import annotations

from dataclasses import dataclass
import json
import math
import random
import time
from pathlib import Path
from typing import Any, Callable, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class VoxelExampleRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    example_id: str
    split: Literal["train", "test", "val"] = "train"
    source_path: str
    voxel_path: str
    resolution: int
    filled_voxels: int
    occupancy_ratio: float
    bbox_fill_ratio: float
    normalization: dict[str, Any]


class VoxelPrepareManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_dir: str
    output_dir: str
    scanned_obj: int
    written: int
    failed: int
    resolution: int
    max_examples: int | None
    split_counts: dict[str, int]


class VoxelDiffusionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_type: Literal["voxel_diffusion_sample"] = "voxel_diffusion_sample"
    sample_id: str
    experiment_id: str
    timestamp_utc: str
    checkpoint_path: str
    seed: int
    resolution: int
    threshold: float
    artifacts: dict[str, str]
    metrics: dict[str, float | int | bool | None]
    export_error: str | None
    elapsed_ms: int


class VoxelEvalSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    renderable: int
    nonempty: int
    mean_occupancy_ratio: float | None
    mean_largest_component_ratio: float | None
    mean_novelty_iou_nearest: float | None


@dataclass(frozen=True)
class VoxelTrainSummary:
    steps: int
    checkpoint_path: Path
    device: str
    examples: int
    elapsed_seconds: float


def timestamp_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def require_voxel_deps() -> tuple[Any, Any, Any]:
    try:
        import numpy as np
        import trimesh
        from skimage import measure
    except ImportError as exc:
        raise RuntimeError(
            "voxel diffusion requires optional geometry deps. "
            "Install with `pip install -e .[voxel-diffusion]`."
        ) from exc
    return np, trimesh, measure


def prepare_voxel_dataset(
    source_dir: Path,
    output_dir: Path,
    *,
    resolution: int = 64,
    max_examples: int | None = None,
    margin: float = 0.05,
) -> VoxelPrepareManifest:
    np, trimesh, _ = require_voxel_deps()
    if resolution < 8:
        raise ValueError("resolution must be at least 8")
    if not source_dir.exists():
        raise ValueError(f"source_dir does not exist: {source_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    voxel_dir = output_dir / "voxels"
    voxel_dir.mkdir(parents=True, exist_ok=True)
    failures_path = output_dir / "failures.jsonl"
    split_handles = {
        "train": (output_dir / "train.jsonl").open("w", encoding="utf-8"),
        "test": (output_dir / "test.jsonl").open("w", encoding="utf-8"),
        "val": (output_dir / "val.jsonl").open("w", encoding="utf-8"),
    }
    split_map = load_fusion_split_map(source_dir)
    obj_paths = sorted(source_dir.rglob("*.obj"))
    if max_examples is not None:
        obj_paths = obj_paths[:max_examples]

    written = 0
    failed = 0
    split_counts = {"train": 0, "test": 0, "val": 0}
    try:
        with failures_path.open("w", encoding="utf-8") as failure_handle:
            for obj_path in obj_paths:
                example_id = obj_path.stem
                split = split_map.get(example_id, "train")
                try:
                    mesh, normalization = load_normalized_mesh(
                        obj_path,
                        trimesh=trimesh,
                        margin=margin,
                    )
                    voxels = mesh_to_voxels(mesh, resolution=resolution, np=np)
                    filled = int(voxels.sum())
                    if filled <= 0:
                        raise ValueError("voxelization produced an empty grid")
                    voxel_path = voxel_dir / f"{example_id}.npz"
                    np.savez_compressed(voxel_path, voxels=voxels.astype(np.bool_))
                    metrics = voxel_basic_metrics(voxels)
                    record = VoxelExampleRecord(
                        example_id=example_id,
                        split=split,
                        source_path=obj_path.as_posix(),
                        voxel_path=voxel_path.as_posix(),
                        resolution=resolution,
                        filled_voxels=filled,
                        occupancy_ratio=float(metrics["occupancy_ratio"]),
                        bbox_fill_ratio=float(metrics["bbox_fill_ratio"]),
                        normalization=normalization,
                    )
                    split_handles[split].write(record.model_dump_json() + "\n")
                    split_counts[split] += 1
                    written += 1
                except Exception as exc:  # noqa: BLE001 - failures are dataset data.
                    failed += 1
                    failure_handle.write(
                        json.dumps(
                            {
                                "example_id": example_id,
                                "source_path": obj_path.as_posix(),
                                "reason": str(exc),
                            }
                        )
                        + "\n"
                    )
    finally:
        for handle in split_handles.values():
            handle.close()

    manifest = VoxelPrepareManifest(
        source_dir=source_dir.as_posix(),
        output_dir=output_dir.as_posix(),
        scanned_obj=len(obj_paths),
        written=written,
        failed=failed,
        resolution=resolution,
        max_examples=max_examples,
        split_counts=split_counts,
    )
    (output_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def load_fusion_split_map(source_dir: Path) -> dict[str, Literal["train", "test", "val"]]:
    for parent in [source_dir, *source_dir.parents]:
        path = parent / "train_test.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            result: dict[str, Literal["train", "test", "val"]] = {}
            if isinstance(data, dict):
                for split in ("train", "test", "val"):
                    values = data.get(split, [])
                    if isinstance(values, list):
                        for value in values:
                            result[str(value)] = split  # type: ignore[assignment]
            return result
    return {}


def load_normalized_mesh(obj_path: Path, *, trimesh: Any, margin: float) -> tuple[Any, dict[str, Any]]:
    loaded = trimesh.load(obj_path, force="scene")
    if hasattr(loaded, "geometry"):
        meshes = [mesh for mesh in loaded.geometry.values() if len(mesh.vertices) and len(mesh.faces)]
        if not meshes:
            raise ValueError("OBJ scene has no mesh geometry")
        mesh = trimesh.util.concatenate(meshes)
    else:
        mesh = loaded
    if not len(mesh.vertices) or not len(mesh.faces):
        raise ValueError("OBJ mesh has no vertices or faces")
    bounds = mesh.bounds
    center = ((bounds[0] + bounds[1]) / 2.0).tolist()
    extents = (bounds[1] - bounds[0]).tolist()
    max_extent = max(float(value) for value in extents)
    if max_extent <= 0:
        raise ValueError("OBJ mesh has zero extent")
    scale = (1.0 - 2.0 * margin) / max_extent
    mesh = mesh.copy()
    mesh.apply_translation([-center[0], -center[1], -center[2]])
    mesh.apply_scale(scale)
    mesh.apply_translation([0.5, 0.5, 0.5])
    return mesh, {
        "source_bounds": bounds.tolist(),
        "source_center": center,
        "source_extents": extents,
        "scale": scale,
        "margin": margin,
    }


def mesh_to_voxels(mesh: Any, *, resolution: int, np: Any) -> Any:
    pitch = 1.0 / float(resolution)
    voxel_grid = mesh.voxelized(pitch)
    try:
        voxel_grid = voxel_grid.fill()
    except Exception:
        pass
    points = voxel_grid.points
    matrix = np.zeros((resolution, resolution, resolution), dtype=np.bool_)
    if len(points) == 0:
        return matrix
    indices = np.floor(points * resolution).astype(int)
    indices = np.clip(indices, 0, resolution - 1)
    matrix[indices[:, 0], indices[:, 1], indices[:, 2]] = True
    return matrix


def load_voxel_examples(data_dir: Path, *, split: str = "train") -> list[VoxelExampleRecord]:
    path = data_dir / f"{split}.jsonl"
    if not path.exists():
        raise ValueError(f"Voxel split does not exist: {path}")
    examples: list[VoxelExampleRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                examples.append(VoxelExampleRecord.model_validate_json(line))
    if not examples:
        raise ValueError(f"Voxel split is empty: {path}")
    return examples


def load_voxel_array(path: Path) -> Any:
    np, _, _ = require_voxel_deps()
    with np.load(path) as data:
        return data["voxels"].astype(np.bool_)


def voxel_basic_metrics(voxels: Any) -> dict[str, float | int | bool | None]:
    np, _, _ = require_voxel_deps()
    occupied = voxels.astype(bool)
    total = int(occupied.size)
    filled = int(occupied.sum())
    occupancy_ratio = filled / total if total else 0.0
    if filled == 0:
        return {
            "filled_voxels": 0,
            "occupancy_ratio": 0.0,
            "bbox_fill_ratio": 0.0,
        }
    coords = np.argwhere(occupied)
    mins = coords.min(axis=0)
    maxs = coords.max(axis=0)
    bbox_shape = maxs - mins + 1
    bbox_volume = int(bbox_shape[0] * bbox_shape[1] * bbox_shape[2])
    return {
        "filled_voxels": filled,
        "occupancy_ratio": occupancy_ratio,
        "bbox_fill_ratio": filled / max(bbox_volume, 1),
    }


def voxel_discriminator_metrics(
    voxels: Any,
    *,
    mesh: Any | None = None,
    training_voxels: list[Any] | None = None,
) -> dict[str, float | int | bool | None]:
    np, _, measure = require_voxel_deps()
    metrics = dict(voxel_basic_metrics(voxels))
    occupied = voxels.astype(bool)
    if int(occupied.sum()) == 0:
        metrics.update(
            {
                "connected_components": 0,
                "largest_component_ratio": 0.0,
                "surface_area": None,
                "mesh_volume": None,
                "watertight": False,
                "euler_number": None,
                "novelty_iou_nearest": None,
                "renderable": False,
            }
        )
        return metrics
    try:
        from scipy import ndimage

        labels, count = ndimage.label(occupied)
        sizes = np.bincount(labels.reshape(-1))
        largest = int(sizes[1:].max()) if len(sizes) > 1 else 0
        metrics["connected_components"] = int(count)
        metrics["largest_component_ratio"] = largest / max(int(occupied.sum()), 1)
    except Exception:
        metrics["connected_components"] = None
        metrics["largest_component_ratio"] = None
    try:
        metrics["euler_number"] = int(measure.euler_number(occupied))
    except Exception:
        metrics["euler_number"] = None
    if mesh is not None:
        metrics["surface_area"] = float(getattr(mesh, "area", 0.0))
        metrics["mesh_volume"] = float(getattr(mesh, "volume", 0.0))
        metrics["watertight"] = bool(getattr(mesh, "is_watertight", False))
        metrics["renderable"] = True
    else:
        metrics["surface_area"] = None
        metrics["mesh_volume"] = None
        metrics["watertight"] = False
        metrics["renderable"] = False
    if training_voxels:
        metrics["novelty_iou_nearest"] = 1.0 - max(voxel_iou(occupied, candidate) for candidate in training_voxels)
    else:
        metrics["novelty_iou_nearest"] = None
    return metrics


def voxel_iou(left: Any, right: Any) -> float:
    np, _, _ = require_voxel_deps()
    l = left.astype(bool)
    r = right.astype(bool)
    intersection = int(np.logical_and(l, r).sum())
    union = int(np.logical_or(l, r).sum())
    return intersection / union if union else 0.0


def voxels_to_mesh(voxels: Any, *, threshold: float = 0.5) -> Any:
    np, trimesh, measure = require_voxel_deps()
    volume = voxels.astype(float)
    if volume.max() <= threshold:
        raise ValueError("voxel grid is empty at threshold")
    padded = np.pad(volume, 1, mode="constant", constant_values=0.0)
    verts, faces, normals, _ = measure.marching_cubes(padded, level=threshold)
    verts = (verts - 1.0) / float(voxels.shape[0])
    return trimesh.Trimesh(vertices=verts, faces=faces, vertex_normals=normals, process=False)


def export_voxel_artifacts(
    voxels: Any,
    artifact_dir: Path,
    *,
    threshold: float = 0.5,
    training_voxels: list[Any] | None = None,
) -> tuple[dict[str, str], dict[str, float | int | bool | None], str | None]:
    np, _, _ = require_voxel_deps()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    voxel_path = artifact_dir / "voxels.npz"
    stl_path = artifact_dir / "raw.stl"
    preview_path = artifact_dir / "preview.png"
    metrics_path = artifact_dir / "metrics.json"
    np.savez_compressed(voxel_path, voxels=voxels.astype(np.bool_))
    artifacts = {"voxels": voxel_path.as_posix()}
    export_error = None
    mesh = None
    try:
        mesh = voxels_to_mesh(voxels, threshold=threshold)
        mesh.export(stl_path)
        artifacts["stl"] = stl_path.as_posix()
        try:
            from cadybara.cadquery_runner import render_stl_preview

            render_stl_preview(stl_path, preview_path)
            artifacts["preview_png"] = preview_path.as_posix()
        except Exception:
            pass
    except Exception as exc:  # noqa: BLE001 - recorded as sample data.
        export_error = str(exc)
    metrics = voxel_discriminator_metrics(voxels, mesh=mesh, training_voxels=training_voxels)
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    artifacts["metrics"] = metrics_path.as_posix()
    return artifacts, metrics, export_error


def latest_voxel_checkpoint(output_dir: Path) -> Path | None:
    checkpoints = sorted(output_dir.glob("checkpoint_step_*.pt"))
    return checkpoints[-1] if checkpoints else None


def train_voxel_diffusion_model(
    data_dir: Path,
    output_dir: Path,
    *,
    resolution: int = 64,
    max_steps: int = 1000,
    batch_size: int = 1,
    base_channels: int = 16,
    timesteps: int = 1000,
    learning_rate: float = 2e-4,
    checkpoint_interval: int = 100,
    time_limit_minutes: float = 480.0,
    seed: int = 0,
    resume: bool = True,
    should_stop: Callable[[], bool] | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> VoxelTrainSummary:
    try:
        import torch
        from torch import nn
        from torch.nn import functional as F
    except ImportError as exc:
        raise RuntimeError(
            "voxel diffusion training requires PyTorch. Install with `pip install -e .[voxel-diffusion]`."
        ) from exc
    np, _, _ = require_voxel_deps()
    random.seed(seed)
    torch.manual_seed(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    examples = load_voxel_examples(data_dir, split="train")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = _build_voxel_unet(nn, base_channels=base_channels).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    start_step = 0
    checkpoint = latest_voxel_checkpoint(output_dir) if resume else None
    if checkpoint is not None:
        payload = torch.load(checkpoint, map_location=device)
        model.load_state_dict(payload["model_state"])
        optimizer.load_state_dict(payload["optimizer_state"])
        start_step = int(payload.get("step", 0))
    betas = torch.linspace(1e-4, 0.02, timesteps, device=device)
    alphas = 1.0 - betas
    alpha_bars = torch.cumprod(alphas, dim=0)
    started = time.perf_counter()
    deadline = started + (time_limit_minutes * 60)
    step = start_step
    checkpoint_path = checkpoint or (output_dir / "checkpoint_step_000000.pt")
    last_loss: float | None = None

    def emit(phase: str) -> None:
        if on_progress is not None:
            on_progress(
                {
                    "phase": phase,
                    "step": step,
                    "max_steps": max_steps,
                    "checkpoint_path": checkpoint_path.as_posix(),
                    "device": device,
                    "examples": len(examples),
                    "loss": last_loss,
                    "elapsed_seconds": time.perf_counter() - started,
                    "resolution": resolution,
                }
            )

    emit("started")
    while (
        step < max_steps
        and time.perf_counter() < deadline
        and not (should_stop is not None and should_stop())
    ):
        batch_records = [random.choice(examples) for _ in range(batch_size)]
        arrays = [np.load(Path(record.voxel_path))["voxels"].astype("float32") for record in batch_records]
        x0 = torch.tensor(np.stack(arrays), dtype=torch.float32, device=device).unsqueeze(1)
        if x0.shape[-1] != resolution:
            raise ValueError(f"expected resolution {resolution}, got {x0.shape[-1]}")
        x0 = x0.mul(2.0).sub(1.0)
        t = torch.randint(0, timesteps, (x0.shape[0],), device=device)
        noise = torch.randn_like(x0)
        a = alpha_bars[t].view(-1, 1, 1, 1, 1)
        noisy = torch.sqrt(a) * x0 + torch.sqrt(1.0 - a) * noise
        pred = model(noisy, t.float() / max(timesteps - 1, 1))
        loss = F.mse_loss(pred, noise)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        step += 1
        last_loss = float(loss.detach().cpu().item())
        emit("training")
        if step % checkpoint_interval == 0 or step == max_steps:
            checkpoint_path = save_voxel_checkpoint(
                output_dir,
                step=step,
                model=model,
                optimizer=optimizer,
                resolution=resolution,
                base_channels=base_channels,
                timesteps=timesteps,
                loss=last_loss,
            )
            emit("checkpoint")

    if step != start_step and (not checkpoint_path.exists() or step % checkpoint_interval != 0):
        checkpoint_path = save_voxel_checkpoint(
            output_dir,
            step=step,
            model=model,
            optimizer=optimizer,
            resolution=resolution,
            base_channels=base_channels,
            timesteps=timesteps,
            loss=last_loss,
        )
        emit("checkpoint")
    emit("stopped" if should_stop is not None and should_stop() else "complete")
    return VoxelTrainSummary(
        steps=step,
        checkpoint_path=checkpoint_path,
        device=device,
        examples=len(examples),
        elapsed_seconds=time.perf_counter() - started,
    )


def _build_voxel_unet(nn: Any, *, base_channels: int):
    class Block(nn.Module):  # type: ignore[misc, valid-type]
        def __init__(self, in_channels: int, out_channels: int) -> None:
            super().__init__()
            self.net = nn.Sequential(
                nn.Conv3d(in_channels, out_channels, 3, padding=1),
                nn.GroupNorm(4, out_channels),
                nn.SiLU(),
                nn.Conv3d(out_channels, out_channels, 3, padding=1),
                nn.GroupNorm(4, out_channels),
                nn.SiLU(),
            )

        def forward(self, x: Any) -> Any:
            return self.net(x)

    class TinyVoxelUNet(nn.Module):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            super().__init__()
            c = base_channels
            self.time = nn.Sequential(nn.Linear(1, c), nn.SiLU(), nn.Linear(c, c))
            self.in_conv = nn.Conv3d(1, c, 3, padding=1)
            self.down1 = Block(c, c)
            self.down2 = Block(c, c * 2)
            self.down3 = Block(c * 2, c * 4)
            self.pool = nn.AvgPool3d(2)
            self.up2 = nn.ConvTranspose3d(c * 4, c * 2, 2, stride=2)
            self.dec2 = Block(c * 4, c * 2)
            self.up1 = nn.ConvTranspose3d(c * 2, c, 2, stride=2)
            self.dec1 = Block(c * 2, c)
            self.out = nn.Conv3d(c, 1, 1)

        def forward(self, x: Any, t: Any) -> Any:
            emb = self.time(t.view(-1, 1)).view(-1, base_channels, 1, 1, 1)
            x = self.in_conv(x) + emb
            d1 = self.down1(x)
            d2 = self.down2(self.pool(d1))
            b = self.down3(self.pool(d2))
            u2 = self.up2(b)
            u2 = self.dec2(torch_cat(nn, u2, d2))
            u1 = self.up1(u2)
            u1 = self.dec1(torch_cat(nn, u1, d1))
            return self.out(u1)

    return TinyVoxelUNet()


def torch_cat(nn: Any, left: Any, right: Any) -> Any:
    import torch

    return torch.cat([left, right], dim=1)


def save_voxel_checkpoint(
    output_dir: Path,
    *,
    step: int,
    model: Any,
    optimizer: Any,
    resolution: int,
    base_channels: int,
    timesteps: int,
    loss: float | None,
) -> Path:
    import torch

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"checkpoint_step_{step:06d}.pt"
    torch.save(
        {
            "step": step,
            "model_state": model.state_dict(),
            "optimizer_state": optimizer.state_dict(),
            "resolution": resolution,
            "model_config": {
                "base_channels": base_channels,
                "timesteps": timesteps,
            },
            "loss": loss,
        },
        path,
    )
    return path


def sample_voxel_diffusion_model(
    checkpoint_path: Path,
    run_dir: Path,
    *,
    count: int = 10,
    sample_steps: int = 50,
    threshold: float = 0.5,
    seed: int = 0,
    data_dir: Path | None = None,
) -> list[VoxelDiffusionRecord]:
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "voxel diffusion sampling requires PyTorch. Install with `pip install -e .[voxel-diffusion]`."
        ) from exc
    np, _, _ = require_voxel_deps()
    if not checkpoint_path.exists():
        raise ValueError(f"Checkpoint does not exist: {checkpoint_path}")
    payload = torch.load(checkpoint_path, map_location="cpu")
    resolution = int(payload["resolution"])
    config = payload["model_config"]
    from torch import nn

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = _build_voxel_unet(nn, base_channels=int(config["base_channels"])).to(device)
    model.load_state_dict(payload["model_state"])
    model.eval()
    timesteps = int(config["timesteps"])
    training_voxels = load_training_voxels(data_dir, limit=128) if data_dir is not None else []
    betas = torch.linspace(1e-4, 0.02, timesteps, device=device)
    alphas = 1.0 - betas
    alpha_bars = torch.cumprod(alphas, dim=0)
    step_indices = torch.linspace(timesteps - 1, 0, sample_steps, device=device).long()
    run_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = run_dir / "results.jsonl"
    records: list[VoxelDiffusionRecord] = []
    generator = torch.Generator(device=device).manual_seed(seed)
    experiment_id = run_dir.name
    with jsonl_path.open("a", encoding="utf-8") as handle:
        for index in range(count):
            started = time.perf_counter()
            sample_seed = seed + index
            generator.manual_seed(sample_seed)
            x = torch.randn((1, 1, resolution, resolution, resolution), device=device, generator=generator)
            with torch.no_grad():
                for t in step_indices:
                    t_batch = torch.full((1,), float(t.item()) / max(timesteps - 1, 1), device=device)
                    pred_noise = model(x, t_batch)
                    a = alpha_bars[t]
                    x0 = (x - torch.sqrt(1.0 - a) * pred_noise) / torch.sqrt(a)
                    if int(t.item()) > 0:
                        prev_t = max(int(t.item()) - max(timesteps // sample_steps, 1), 0)
                        prev_a = alpha_bars[prev_t]
                        x = torch.sqrt(prev_a) * x0 + torch.sqrt(1.0 - prev_a) * pred_noise
                    else:
                        x = x0
            probs = ((x.clamp(-1, 1) + 1.0) / 2.0)[0, 0].detach().cpu().numpy()
            voxels = probs >= threshold
            sample_id = str(uuid4())
            artifact_dir = run_dir / "artifacts" / sample_id[:8]
            artifacts, metrics, export_error = export_voxel_artifacts(
                voxels,
                artifact_dir,
                threshold=threshold,
                training_voxels=training_voxels,
            )
            record = VoxelDiffusionRecord(
                sample_id=sample_id,
                experiment_id=experiment_id,
                timestamp_utc=timestamp_utc(),
                checkpoint_path=checkpoint_path.as_posix(),
                seed=sample_seed,
                resolution=resolution,
                threshold=threshold,
                artifacts=artifacts,
                metrics=metrics,
                export_error=export_error,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )
            handle.write(record.model_dump_json() + "\n")
            handle.flush()
            records.append(record)
    return records


def load_training_voxels(data_dir: Path | None, *, limit: int = 128) -> list[Any]:
    if data_dir is None:
        return []
    try:
        examples = load_voxel_examples(data_dir, split="train")[:limit]
        return [load_voxel_array(Path(example.voxel_path)) for example in examples]
    except Exception:
        return []


def eval_voxel_diffusion_run(run_dir: Path) -> VoxelEvalSummary:
    path = run_dir / "results.jsonl"
    if not path.exists():
        raise ValueError(f"Voxel run results do not exist: {path}")
    records: list[VoxelDiffusionRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(VoxelDiffusionRecord.model_validate_json(line))
    occupancies = [
        float(record.metrics["occupancy_ratio"])
        for record in records
        if isinstance(record.metrics.get("occupancy_ratio"), (float, int))
    ]
    largest = [
        float(record.metrics["largest_component_ratio"])
        for record in records
        if isinstance(record.metrics.get("largest_component_ratio"), (float, int))
    ]
    novelty = [
        float(record.metrics["novelty_iou_nearest"])
        for record in records
        if isinstance(record.metrics.get("novelty_iou_nearest"), (float, int))
    ]
    return VoxelEvalSummary(
        total=len(records),
        renderable=sum(1 for record in records if bool(record.artifacts.get("stl")) and record.export_error is None),
        nonempty=sum(1 for record in records if float(record.metrics.get("occupancy_ratio") or 0.0) > 0.0),
        mean_occupancy_ratio=(sum(occupancies) / len(occupancies) if occupancies else None),
        mean_largest_component_ratio=(sum(largest) / len(largest) if largest else None),
        mean_novelty_iou_nearest=(sum(novelty) / len(novelty) if novelty else None),
    )
