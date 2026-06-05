from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from cadybara.cadquery_runner import export_cadquery_code, render_stl_preview


SPECIAL_TOKENS = ["<PAD>", "<BOS>", "<EOS>", "<MASK>", "<UNK>"]
COMMAND_TOKENS = [
    "OP:EXTRUDE",
    "PROFILE:RECT",
    "PROFILE:CIRCLE",
    "MODE:NEW",
    "MODE:JOIN",
    "MODE:CUT",
    "ENDOP",
]
SIGNED_BINS = tuple(range(-100, 105, 5))
POSITIVE_BINS = tuple(range(5, 205, 5))
X_TOKENS = frozenset(_token for _token in (f"X:{value:+04d}" for value in SIGNED_BINS))
Y_TOKENS = frozenset(_token for _token in (f"Y:{value:+04d}" for value in SIGNED_BINS))
W_TOKENS = frozenset(_token for _token in (f"W:{value:03d}" for value in POSITIVE_BINS))
H_TOKENS = frozenset(_token for _token in (f"H:{value:03d}" for value in POSITIVE_BINS))
R_TOKENS = frozenset(_token for _token in (f"R:{value:03d}" for value in POSITIVE_BINS))
D_TOKENS = frozenset(_token for _token in (f"D:{value:03d}" for value in POSITIVE_BINS))


class UnsupportedProgram(ValueError):
    pass


class ExtrudeOp(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: Literal["rect", "circle"]
    mode: Literal["new", "join", "cut"] = "join"
    x: float = 0.0
    y: float = 0.0
    width: float | None = None
    height: float | None = None
    radius: float | None = None
    distance: float = Field(gt=0)


class CadProgram(BaseModel):
    model_config = ConfigDict(extra="forbid")

    units: Literal["mm"] = "mm"
    ops: list[ExtrudeOp] = Field(min_length=1)


class PreparedCadExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    example_id: str
    split: Literal["train", "test", "val"] = "train"
    source_path: str
    program: CadProgram
    tokens: list[str]
    token_count: int


class PrepareManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_dir: str
    output_dir: str
    scanned_json: int
    written: int
    unsupported: int
    max_examples: int | None
    max_len: int
    unsupported_reasons: dict[str, int]


class CadDiffusionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_type: Literal["cad_diffusion_sample"] = "cad_diffusion_sample"
    sample_id: str
    experiment_id: str
    timestamp_utc: str
    checkpoint_path: str
    seed: int
    tokens: list[str]
    program: dict[str, Any] | None
    parse_error: str | None
    compile_error: str | None
    render_error: str | None
    artifacts: dict[str, str]
    metrics: dict[str, float | int | str | None]
    nearest_neighbor_distance: float | None
    elapsed_ms: int


class EvalSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    parse_valid: int
    compiled: int
    renderable: int
    unique_token_sequences: int
    unique_programs: int
    mean_nearest_neighbor_distance: float | None


@dataclass(frozen=True)
class TrainSummary:
    steps: int
    checkpoint_path: Path
    device: str
    examples: int
    elapsed_seconds: float


class CadGrammarState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: Literal[
        "start",
        "between_ops",
        "after_op",
        "after_profile",
        "after_mode",
        "after_x",
        "after_y",
        "after_w",
        "after_rect_size",
        "after_circle_size",
        "after_d",
        "after_eos",
    ] = "start"
    op_count: int = 0
    profile: Literal["rect", "circle"] | None = None


class CadTokenVocab:
    def __init__(self, tokens: list[str] | None = None) -> None:
        if tokens is None:
            tokens = default_vocab_tokens()
        self.tokens = list(tokens)
        self.token_to_id = {token: index for index, token in enumerate(self.tokens)}

    @property
    def pad_id(self) -> int:
        return self.token_to_id["<PAD>"]

    @property
    def bos_id(self) -> int:
        return self.token_to_id["<BOS>"]

    @property
    def eos_id(self) -> int:
        return self.token_to_id["<EOS>"]

    @property
    def mask_id(self) -> int:
        return self.token_to_id["<MASK>"]

    @property
    def unk_id(self) -> int:
        return self.token_to_id["<UNK>"]

    def __len__(self) -> int:
        return len(self.tokens)

    def encode(self, tokens: list[str], *, max_len: int) -> list[int]:
        ids = [self.token_to_id.get(token, self.unk_id) for token in tokens[:max_len]]
        if len(ids) < max_len:
            ids.extend([self.pad_id] * (max_len - len(ids)))
        return ids

    def decode(self, ids: list[int]) -> list[str]:
        result: list[str] = []
        for item in ids:
            if item < 0 or item >= len(self.tokens):
                result.append("<UNK>")
            else:
                result.append(self.tokens[item])
        return result

    def sample_allowed_ids(self) -> list[int]:
        disallowed = {"<PAD>", "<BOS>", "<MASK>", "<UNK>"}
        return [index for index, token in enumerate(self.tokens) if token not in disallowed]


def default_vocab_tokens() -> list[str]:
    tokens = [*SPECIAL_TOKENS, *COMMAND_TOKENS]
    for prefix in ("X", "Y"):
        tokens.extend(_signed_token(prefix, value) for value in SIGNED_BINS)
    for prefix in ("W", "H", "R", "D"):
        tokens.extend(_positive_token(prefix, value) for value in POSITIVE_BINS)
    return tokens


def timestamp_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def quantize_signed(value: float) -> int:
    return min(SIGNED_BINS, key=lambda item: abs(item - value))


def quantize_positive(value: float) -> int:
    if value <= 0:
        raise UnsupportedProgram(f"positive CAD dimension required, got {value}")
    return min(POSITIVE_BINS, key=lambda item: abs(item - value))


def _signed_token(prefix: str, value: int) -> str:
    return f"{prefix}:{value:+04d}"


def _positive_token(prefix: str, value: int) -> str:
    return f"{prefix}:{value:03d}"


def _parse_numeric_token(token: str, prefix: str) -> int:
    expected = f"{prefix}:"
    if not token.startswith(expected):
        raise UnsupportedProgram(f"expected {prefix} token, got {token}")
    try:
        return int(token[len(expected) :])
    except ValueError as exc:
        raise UnsupportedProgram(f"invalid numeric token {token}") from exc


def cad_grammar_allowed_next(tokens: list[str], *, max_len: int = 256) -> set[str]:
    state = _cad_grammar_state(tokens, max_len=max_len)
    if len(tokens) >= max_len and state.phase != "after_eos":
        return set()
    if state.phase == "start":
        return {"<BOS>"}
    if state.phase == "between_ops":
        return {"OP:EXTRUDE"} if state.op_count == 0 else {"OP:EXTRUDE", "<EOS>"}
    if state.phase == "after_op":
        return {"PROFILE:RECT", "PROFILE:CIRCLE"}
    if state.phase == "after_profile":
        if state.op_count == 0:
            return {"MODE:NEW", "MODE:JOIN"}
        return {"MODE:NEW", "MODE:JOIN", "MODE:CUT"}
    if state.phase == "after_mode":
        return set(X_TOKENS)
    if state.phase == "after_x":
        return set(Y_TOKENS)
    if state.phase == "after_y":
        return set(W_TOKENS if state.profile == "rect" else R_TOKENS)
    if state.phase == "after_w":
        return set(H_TOKENS)
    if state.phase in {"after_rect_size", "after_circle_size"}:
        return set(D_TOKENS)
    if state.phase == "after_d":
        return {"ENDOP"}
    if state.phase == "after_eos":
        return {"<PAD>"}
    return set()


def validate_cad_token_grammar(tokens: list[str], *, max_len: int = 256) -> None:
    if len(tokens) > max_len:
        raise UnsupportedProgram(f"token sequence length {len(tokens)} exceeds max_len={max_len}")
    prefix: list[str] = []
    for index, token in enumerate(tokens):
        allowed = cad_grammar_allowed_next(prefix, max_len=max_len)
        if token not in allowed:
            raise UnsupportedProgram(
                f"grammar token {index}: expected {_describe_expected_tokens(allowed)}, got {token}"
            )
        prefix.append(token)
    allowed = cad_grammar_allowed_next(prefix, max_len=max_len)
    if allowed != {"<PAD>"}:
        raise UnsupportedProgram(
            f"token sequence ended before <EOS>; expected {_describe_expected_tokens(allowed)}"
        )


def _cad_grammar_state(tokens: list[str], *, max_len: int) -> CadGrammarState:
    if len(tokens) > max_len:
        raise UnsupportedProgram(f"token sequence length {len(tokens)} exceeds max_len={max_len}")
    state = CadGrammarState()
    for index, token in enumerate(tokens):
        allowed = _allowed_next_for_state(state)
        if token not in allowed:
            raise UnsupportedProgram(
                f"grammar token {index}: expected {_describe_expected_tokens(allowed)}, got {token}"
            )
        state = _advance_grammar_state(state, token)
    return state


def _allowed_next_for_state(state: CadGrammarState) -> set[str]:
    if state.phase == "start":
        return {"<BOS>"}
    if state.phase == "between_ops":
        return {"OP:EXTRUDE"} if state.op_count == 0 else {"OP:EXTRUDE", "<EOS>"}
    if state.phase == "after_op":
        return {"PROFILE:RECT", "PROFILE:CIRCLE"}
    if state.phase == "after_profile":
        if state.op_count == 0:
            return {"MODE:NEW", "MODE:JOIN"}
        return {"MODE:NEW", "MODE:JOIN", "MODE:CUT"}
    if state.phase == "after_mode":
        return set(X_TOKENS)
    if state.phase == "after_x":
        return set(Y_TOKENS)
    if state.phase == "after_y":
        return set(W_TOKENS if state.profile == "rect" else R_TOKENS)
    if state.phase == "after_w":
        return set(H_TOKENS)
    if state.phase in {"after_rect_size", "after_circle_size"}:
        return set(D_TOKENS)
    if state.phase == "after_d":
        return {"ENDOP"}
    if state.phase == "after_eos":
        return {"<PAD>"}
    return set()


def _advance_grammar_state(state: CadGrammarState, token: str) -> CadGrammarState:
    if state.phase == "start":
        return CadGrammarState(phase="between_ops", op_count=state.op_count)
    if state.phase == "between_ops":
        if token == "<EOS>":
            return state.model_copy(update={"phase": "after_eos"})
        return state.model_copy(update={"phase": "after_op", "profile": None})
    if state.phase == "after_op":
        profile = "rect" if token == "PROFILE:RECT" else "circle"
        return state.model_copy(update={"phase": "after_profile", "profile": profile})
    if state.phase == "after_profile":
        return state.model_copy(update={"phase": "after_mode"})
    if state.phase == "after_mode":
        return state.model_copy(update={"phase": "after_x"})
    if state.phase == "after_x":
        return state.model_copy(update={"phase": "after_y"})
    if state.phase == "after_y":
        return state.model_copy(
            update={"phase": "after_w" if state.profile == "rect" else "after_circle_size"}
        )
    if state.phase == "after_w":
        return state.model_copy(update={"phase": "after_rect_size"})
    if state.phase in {"after_rect_size", "after_circle_size"}:
        return state.model_copy(update={"phase": "after_d"})
    if state.phase == "after_d":
        return CadGrammarState(phase="between_ops", op_count=state.op_count + 1)
    if state.phase == "after_eos":
        return state
    return state


def _describe_expected_tokens(tokens: set[str]) -> str:
    if not tokens:
        return "<none>"
    groups = [
        (X_TOKENS, "X token"),
        (Y_TOKENS, "Y token"),
        (W_TOKENS, "W token"),
        (H_TOKENS, "H token"),
        (R_TOKENS, "R token"),
        (D_TOKENS, "D token"),
    ]
    for group, label in groups:
        if tokens == group:
            return label
    return " or ".join(sorted(tokens))


def program_to_tokens(program: CadProgram, *, max_len: int = 256) -> list[str]:
    tokens = ["<BOS>"]
    for op in program.ops:
        tokens.extend(["OP:EXTRUDE", f"PROFILE:{op.profile.upper()}", f"MODE:{op.mode.upper()}"])
        tokens.extend(
            [
                _signed_token("X", quantize_signed(op.x)),
                _signed_token("Y", quantize_signed(op.y)),
            ]
        )
        if op.profile == "rect":
            if op.width is None or op.height is None:
                raise UnsupportedProgram("rect extrude requires width and height")
            tokens.extend(
                [
                    _positive_token("W", quantize_positive(op.width)),
                    _positive_token("H", quantize_positive(op.height)),
                ]
            )
        else:
            if op.radius is None:
                raise UnsupportedProgram("circle extrude requires radius")
            tokens.append(_positive_token("R", quantize_positive(op.radius)))
        tokens.extend([_positive_token("D", quantize_positive(op.distance)), "ENDOP"])
    tokens.append("<EOS>")
    if len(tokens) > max_len:
        raise UnsupportedProgram(f"token sequence length {len(tokens)} exceeds max_len={max_len}")
    validate_cad_token_grammar(tokens, max_len=max_len)
    return tokens


def tokens_to_program(tokens: list[str]) -> CadProgram:
    validate_cad_token_grammar(tokens)
    cleaned: list[str] = []
    for token in tokens:
        if token == "<PAD>":
            continue
        cleaned.append(token)
        if token == "<EOS>":
            break
    if not cleaned or cleaned[0] != "<BOS>":
        raise UnsupportedProgram("token sequence must start with <BOS>")
    ops: list[ExtrudeOp] = []
    index = 1
    while index < len(cleaned):
        token = cleaned[index]
        if token == "<EOS>":
            break
        if token != "OP:EXTRUDE":
            raise UnsupportedProgram(f"expected OP:EXTRUDE, got {token}")
        try:
            profile_token = cleaned[index + 1]
            mode_token = cleaned[index + 2]
            x_token = cleaned[index + 3]
            y_token = cleaned[index + 4]
        except IndexError as exc:
            raise UnsupportedProgram("truncated extrude operation") from exc

        if profile_token not in {"PROFILE:RECT", "PROFILE:CIRCLE"}:
            raise UnsupportedProgram(f"unsupported profile token {profile_token}")
        if mode_token not in {"MODE:NEW", "MODE:JOIN", "MODE:CUT"}:
            raise UnsupportedProgram(f"unsupported mode token {mode_token}")

        profile = "rect" if profile_token == "PROFILE:RECT" else "circle"
        mode = mode_token.removeprefix("MODE:").lower()
        x = float(_parse_numeric_token(x_token, "X"))
        y = float(_parse_numeric_token(y_token, "Y"))
        cursor = index + 5
        if profile == "rect":
            try:
                width = float(_parse_numeric_token(cleaned[cursor], "W"))
                height = float(_parse_numeric_token(cleaned[cursor + 1], "H"))
                distance = float(_parse_numeric_token(cleaned[cursor + 2], "D"))
                endop = cleaned[cursor + 3]
            except IndexError as exc:
                raise UnsupportedProgram("truncated rect extrude") from exc
            if endop != "ENDOP":
                raise UnsupportedProgram(f"expected ENDOP, got {endop}")
            ops.append(
                ExtrudeOp(
                    profile="rect",
                    mode=mode,  # type: ignore[arg-type]
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    distance=distance,
                )
            )
            index = cursor + 4
        else:
            try:
                radius = float(_parse_numeric_token(cleaned[cursor], "R"))
                distance = float(_parse_numeric_token(cleaned[cursor + 1], "D"))
                endop = cleaned[cursor + 2]
            except IndexError as exc:
                raise UnsupportedProgram("truncated circle extrude") from exc
            if endop != "ENDOP":
                raise UnsupportedProgram(f"expected ENDOP, got {endop}")
            ops.append(
                ExtrudeOp(
                    profile="circle",
                    mode=mode,  # type: ignore[arg-type]
                    x=x,
                    y=y,
                    radius=radius,
                    distance=distance,
                )
            )
            index = cursor + 3
    if not ops:
        raise UnsupportedProgram("program contains no operations")
    return CadProgram(ops=ops)


def program_to_cadquery_code(program: CadProgram) -> str:
    validate_program(program)
    lines = ["import cadquery as cq", "", "result = None"]
    for index, op in enumerate(program.ops):
        name = f"op_{index}"
        if op.profile == "rect":
            lines.append(
                f'{name} = cq.Workplane("XY").center({op.x:.6g}, {op.y:.6g})'
                f".rect({op.width:.6g}, {op.height:.6g}).extrude({op.distance:.6g})"
            )
        else:
            lines.append(
                f'{name} = cq.Workplane("XY").center({op.x:.6g}, {op.y:.6g})'
                f".circle({op.radius:.6g}).extrude({op.distance:.6g})"
            )
        if index == 0:
            if op.mode == "cut":
                raise UnsupportedProgram("first operation cannot be a cut")
            lines.append(f"result = {name}")
        elif op.mode == "cut":
            lines.append(f"result = result.cut({name})")
        else:
            lines.append(f"result = result.union({name})")
    lines.append("")
    return "\n".join(lines)


def validate_program(program: CadProgram) -> None:
    for index, op in enumerate(program.ops):
        if op.distance <= 0:
            raise UnsupportedProgram(f"op {index} distance must be positive")
        if op.profile == "rect":
            if op.width is None or op.height is None:
                raise UnsupportedProgram(f"op {index} rect requires width and height")
            if op.width <= 0 or op.height <= 0:
                raise UnsupportedProgram(f"op {index} rect dimensions must be positive")
        if op.profile == "circle":
            if op.radius is None or op.radius <= 0:
                raise UnsupportedProgram(f"op {index} circle radius must be positive")


def normalize_program_origin(program: CadProgram) -> CadProgram:
    if not program.ops:
        return program
    origin_x = program.ops[0].x
    origin_y = program.ops[0].y
    normalized_ops = [
        op.model_copy(update={"x": op.x - origin_x, "y": op.y - origin_y})
        for op in program.ops
    ]
    return CadProgram(units=program.units, ops=normalized_ops)


def program_metrics(program: CadProgram) -> dict[str, float | int | str | None]:
    min_x = math.inf
    max_x = -math.inf
    min_y = math.inf
    max_y = -math.inf
    max_z = 0.0
    cut_count = 0
    for op in program.ops:
        if op.profile == "rect":
            assert op.width is not None and op.height is not None
            half_w = op.width / 2
            half_h = op.height / 2
        else:
            assert op.radius is not None
            half_w = op.radius
            half_h = op.radius
        min_x = min(min_x, op.x - half_w)
        max_x = max(max_x, op.x + half_w)
        min_y = min(min_y, op.y - half_h)
        max_y = max(max_y, op.y + half_h)
        max_z = max(max_z, op.distance)
        if op.mode == "cut":
            cut_count += 1
    return {
        "operation_count": len(program.ops),
        "cut_count": cut_count,
        "bbox_x_mm": max_x - min_x if min_x != math.inf else None,
        "bbox_y_mm": max_y - min_y if min_y != math.inf else None,
        "bbox_z_mm": max_z,
    }


def compile_program_artifacts(program: CadProgram, artifact_dir: Path) -> tuple[dict[str, str], str | None]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    code = program_to_cadquery_code(program)
    paths = {
        "folder": artifact_dir,
        "tokens": artifact_dir / "tokens.txt",
        "program": artifact_dir / "program.json",
        "cadquery_code": artifact_dir / "model.py",
        "stl": artifact_dir / "model.stl",
        "step": artifact_dir / "model.step",
        "preview_png": artifact_dir / "preview.png",
        "render_error": artifact_dir / "render_error.txt",
        "preview_error": artifact_dir / "preview_error.txt",
    }
    paths["program"].write_text(program.model_dump_json(indent=2) + "\n", encoding="utf-8")
    paths["cadquery_code"].write_text(code, encoding="utf-8")

    render_error: str | None = None
    try:
        export_cadquery_code(code, paths["stl"], paths["step"])
        if paths["render_error"].exists():
            paths["render_error"].unlink()
    except Exception as exc:  # noqa: BLE001 - failure is the experiment signal.
        render_error = str(exc)
        paths["render_error"].write_text(render_error + "\n", encoding="utf-8")
    else:
        try:
            render_stl_preview(paths["stl"], paths["preview_png"])
            if paths["preview_error"].exists():
                paths["preview_error"].unlink()
        except Exception as exc:  # noqa: BLE001 - preview failure is recorded separately.
            paths["preview_error"].write_text(str(exc) + "\n", encoding="utf-8")

    artifacts = {
        name: path.as_posix()
        for name, path in paths.items()
        if name not in {"render_error", "preview_error"}
        and path.exists()
        and (name != "stl" or path.exists())
        and (name != "step" or path.exists())
        and (name != "preview_png" or path.exists())
    }
    if render_error:
        artifacts["render_error"] = paths["render_error"].as_posix()
    if paths["preview_error"].exists():
        artifacts["preview_error"] = paths["preview_error"].as_posix()
    return artifacts, render_error


def prepare_fusion360_dataset(
    dataset_dir: Path,
    output_dir: Path,
    *,
    max_examples: int | None = None,
    max_len: int = 256,
) -> PrepareManifest:
    if not dataset_dir.exists():
        raise ValueError(f"Dataset directory does not exist: {dataset_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    train_path = output_dir / "train.jsonl"
    test_path = output_dir / "test.jsonl"
    val_path = output_dir / "val.jsonl"
    manifest_path = output_dir / "manifest.json"
    unsupported_path = output_dir / "unsupported.jsonl"

    scanned = 0
    written = 0
    unsupported = 0
    unsupported_reasons: dict[str, int] = {}
    split_map = load_train_test_split(dataset_dir)
    handles = {
        "train": train_path.open("w", encoding="utf-8"),
        "test": test_path.open("w", encoding="utf-8"),
        "val": val_path.open("w", encoding="utf-8"),
    }
    unsupported_handle = unsupported_path.open("w", encoding="utf-8")
    try:
        for json_path in sorted(dataset_dir.rglob("*.json")):
            if max_examples is not None and written >= max_examples:
                break
            scanned += 1
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                program = normalize_program_origin(extract_supported_program(data))
                tokens = program_to_tokens(program, max_len=max_len)
            except Exception as exc:  # noqa: BLE001 - unsupported examples are expected.
                unsupported += 1
                reason = type(exc).__name__ + ": " + str(exc).splitlines()[0]
                unsupported_reasons[reason] = unsupported_reasons.get(reason, 0) + 1
                unsupported_handle.write(
                    json.dumps({"source_path": json_path.as_posix(), "reason": reason}) + "\n"
                )
                continue
            split = split_for_path(json_path, dataset_dir, split_map=split_map)
            example = PreparedCadExample(
                example_id=json_path.stem,
                split=split,
                source_path=json_path.as_posix(),
                program=program,
                tokens=tokens,
                token_count=len(tokens),
            )
            handles[split].write(example.model_dump_json() + "\n")
            written += 1
    finally:
        for handle in handles.values():
            handle.close()
        unsupported_handle.close()

    manifest = PrepareManifest(
        dataset_dir=dataset_dir.as_posix(),
        output_dir=output_dir.as_posix(),
        scanned_json=scanned,
        written=written,
        unsupported=unsupported,
        max_examples=max_examples,
        max_len=max_len,
        unsupported_reasons=dict(sorted(unsupported_reasons.items())),
    )
    manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return manifest


def load_train_test_split(dataset_dir: Path) -> dict[str, Literal["train", "test", "val"]]:
    path = dataset_dir / "train_test.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    split_map: dict[str, Literal["train", "test", "val"]] = {}
    if isinstance(data, dict):
        for split_name, names in data.items():
            split = normalize_split_name(split_name)
            if split is None or not isinstance(names, list):
                continue
            for name in names:
                if isinstance(name, str):
                    split_map[_split_key(name)] = split
                    split_map[_split_key(Path(name).stem)] = split
    return split_map


def normalize_split_name(value: Any) -> Literal["train", "test", "val"] | None:
    text = str(value).lower()
    if text in {"train", "training"}:
        return "train"
    if text in {"test", "testing"}:
        return "test"
    if text in {"val", "valid", "validation"}:
        return "val"
    return None


def _split_key(value: str) -> str:
    return value.replace("\\", "/").lower()


def split_for_path(
    json_path: Path,
    dataset_dir: Path,
    *,
    split_map: dict[str, Literal["train", "test", "val"]] | None = None,
) -> Literal["train", "test", "val"]:
    relative = json_path.relative_to(dataset_dir)
    if split_map:
        candidates = [
            _split_key(relative.as_posix()),
            _split_key(json_path.name),
            _split_key(json_path.stem),
        ]
        for candidate in candidates:
            if candidate in split_map:
                return split_map[candidate]
    parts = {part.lower() for part in relative.parts}
    if {"test", "testing"} & parts:
        return "test"
    if {"val", "valid", "validation"} & parts:
        return "val"
    return "train"


def extract_supported_program(data: Any) -> CadProgram:
    if not isinstance(data, dict):
        raise UnsupportedProgram("top-level JSON must be an object")
    if isinstance(data.get("program"), dict):
        return CadProgram.model_validate(data["program"])
    if isinstance(data.get("ops"), list):
        scale = 10.0 if str(data.get("units", "")).lower() == "cm" else 1.0
        return CadProgram(ops=[direct_op_to_extrude(item, scale=scale) for item in data["ops"]])
    ops: list[ExtrudeOp] = []
    if isinstance(data.get("timeline"), list):
        entities = data.get("entities") if isinstance(data.get("entities"), dict) else {}
        for item in data["timeline"]:
            entity = item
            if isinstance(item, dict) and isinstance(item.get("entity"), str):
                entity = entities.get(item["entity"], item)
            if _looks_like_extrude(entity):
                ops.extend(extrude_entity_to_ops(entity, entities=entities, scale=10.0))
    elif isinstance(data.get("sequence"), list):
        entities = data.get("entities") if isinstance(data.get("entities"), dict) else {}
        for item in data["sequence"]:
            entity = item
            if isinstance(item, dict) and isinstance(item.get("entity"), str):
                entity = entities.get(item["entity"], item)
            if _looks_like_extrude(entity):
                ops.extend(extrude_entity_to_ops(entity, entities=entities, scale=10.0))
    elif isinstance(data.get("entities"), dict):
        entities = data["entities"]
        for item in entities.values():
            if _looks_like_extrude(item):
                ops.extend(extrude_entity_to_ops(item, entities=entities, scale=10.0))
    if not ops:
        raise UnsupportedProgram("no directly supported sketch-extrude operations found")
    return CadProgram(ops=ops)


def _looks_like_extrude(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    text = " ".join(str(value.get(key, "")) for key in ("type", "op", "operation", "name")).lower()
    return "extrude" in text or value.get("op") == "extrude"


def extrude_entity_to_ops(
    value: Any,
    *,
    entities: dict[str, Any] | None = None,
    scale: float = 1.0,
) -> list[ExtrudeOp]:
    if not isinstance(value, dict):
        raise UnsupportedProgram("operation must be an object")
    if any(key in value for key in ("profile", "shape", "profile_type", "width", "radius")):
        return [direct_op_to_extrude(value, scale=scale)]
    entities = entities or {}
    profile_refs = value.get("profiles")
    if not isinstance(profile_refs, list) or not profile_refs:
        raise UnsupportedProgram("extrude has no directly readable profiles")
    distance = extract_distance(value) * scale
    mode = normalize_mode(value.get("mode") or value.get("operation") or value.get("operation_type"))
    ops: list[ExtrudeOp] = []
    for profile_ref in profile_refs:
        if not isinstance(profile_ref, dict):
            raise UnsupportedProgram("profile reference must be an object")
        sketch_id = profile_ref.get("sketch")
        profile_id = profile_ref.get("profile")
        sketch = entities.get(sketch_id) if isinstance(sketch_id, str) else None
        if not isinstance(sketch, dict):
            raise UnsupportedProgram("extrude profile references an unavailable sketch")
        profiles = sketch.get("profiles")
        if not isinstance(profiles, dict) or not isinstance(profile_id, str):
            raise UnsupportedProgram("sketch profiles are unavailable")
        profile = profiles.get(profile_id)
        if not isinstance(profile, dict):
            raise UnsupportedProgram("referenced sketch profile is unavailable")
        ops.append(profile_to_extrude_op(profile, mode=mode, distance=distance, scale=scale))
    return ops


def direct_op_to_extrude(value: Any, *, scale: float = 1.0) -> ExtrudeOp:
    if not isinstance(value, dict):
        raise UnsupportedProgram("operation must be an object")
    profile = str(value.get("profile") or value.get("shape") or value.get("profile_type") or "").lower()
    if profile not in {"rect", "rectangle", "circle"}:
        raise UnsupportedProgram(f"unsupported or missing profile: {profile or '<missing>'}")
    mode = normalize_mode(value.get("mode") or value.get("operation") or value.get("operation_type"))
    x = _number_from(value, "x", "center_x", default=0.0)
    y = _number_from(value, "y", "center_y", default=0.0)
    distance = extract_distance(value)
    if profile in {"rect", "rectangle"}:
        return ExtrudeOp(
            profile="rect",
            mode=mode,
            x=x * scale,
            y=y * scale,
            width=_number_from(value, "width", "w", "x_len", "xLen") * scale,
            height=_number_from(value, "height", "h", "y_len", "yLen") * scale,
            distance=distance * scale,
        )
    return ExtrudeOp(
        profile="circle",
        mode=mode,
        x=x * scale,
        y=y * scale,
        radius=_number_from(value, "radius", "r") * scale,
        distance=distance * scale,
    )


def profile_to_extrude_op(
    profile: dict[str, Any],
    *,
    mode: Literal["new", "join", "cut"],
    distance: float,
    scale: float,
) -> ExtrudeOp:
    curves = outer_profile_curves(profile)
    if len(curves) == 1:
        circle = circle_from_curve(curves[0])
        if circle is not None:
            x, y, radius = circle
            return ExtrudeOp(
                profile="circle",
                mode=mode,
                x=x * scale,
                y=y * scale,
                radius=radius * scale,
                distance=distance,
            )
    rectangle = rectangle_from_curves(curves)
    if rectangle is not None:
        x, y, width, height = rectangle
        return ExtrudeOp(
            profile="rect",
            mode=mode,
            x=x * scale,
            y=y * scale,
            width=width * scale,
            height=height * scale,
            distance=distance,
        )
    raise UnsupportedProgram("profile is not a v0 rectangle or circle")


def outer_profile_curves(profile: dict[str, Any]) -> list[dict[str, Any]]:
    loops = profile.get("loops")
    if not isinstance(loops, list):
        raise UnsupportedProgram("profile contains no loops")
    selected = next((loop for loop in loops if isinstance(loop, dict) and loop.get("is_outer")), None)
    if selected is None:
        selected = next((loop for loop in loops if isinstance(loop, dict)), None)
    if not isinstance(selected, dict):
        raise UnsupportedProgram("profile contains no readable outer loop")
    curves = selected.get("profile_curves")
    if not isinstance(curves, list) or not all(isinstance(curve, dict) for curve in curves):
        raise UnsupportedProgram("profile outer loop contains no readable curves")
    return curves


def circle_from_curve(curve: dict[str, Any]) -> tuple[float, float, float] | None:
    curve_type = str(curve.get("type", "")).lower()
    if "circle" not in curve_type:
        return None
    center = curve.get("center") or curve.get("center_point")
    radius = _coerce_number(curve.get("radius"))
    if isinstance(center, dict) and radius is not None:
        point = _point_xy(center)
        if point is not None:
            return point[0], point[1], radius
    return None


def rectangle_from_curves(curves: list[dict[str, Any]]) -> tuple[float, float, float, float] | None:
    if len(curves) != 4:
        return None
    points: list[tuple[float, float]] = []
    for curve in curves:
        curve_type = str(curve.get("type", "")).lower()
        if "line" not in curve_type:
            return None
        start = _point_xy(curve.get("start_point"))
        end = _point_xy(curve.get("end_point"))
        if start is None or end is None:
            return None
        points.extend([start, end])
    xs = sorted({round(point[0], 9) for point in points})
    ys = sorted({round(point[1], 9) for point in points})
    if len(xs) != 2 or len(ys) != 2:
        return None
    width = xs[1] - xs[0]
    height = ys[1] - ys[0]
    if width <= 0 or height <= 0:
        return None
    return (xs[0] + xs[1]) / 2, (ys[0] + ys[1]) / 2, width, height


def _point_xy(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, dict):
        return None
    x = _coerce_number(value.get("x"))
    y = _coerce_number(value.get("y"))
    if x is None or y is None:
        return None
    return x, y


def normalize_mode(value: Any) -> Literal["new", "join", "cut"]:
    text = str(value or "join").lower()
    if "cut" in text:
        return "cut"
    if "new" in text or "create" in text:
        return "new"
    return "join"


def _number_from(value: dict[str, Any], *keys: str, default: float | None = None) -> float:
    for key in keys:
        if key not in value:
            continue
        item = value[key]
        number = _coerce_number(item)
        if number is not None:
            return number
    if default is not None:
        return default
    raise UnsupportedProgram(f"missing numeric field: {'/'.join(keys)}")


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    if isinstance(value, dict):
        for key in ("value", "distance", "real", "magnitude"):
            if key in value:
                number = _coerce_number(value[key])
                if number is not None:
                    return number
    return None


def extract_distance(value: dict[str, Any]) -> float:
    for key in ("distance", "depth", "extent", "extrude_distance"):
        if key in value:
            number = _coerce_number(value[key])
            if number is not None:
                return abs(number)
    for key in ("extent_one", "extentOne", "extent_two", "extentTwo"):
        item = value.get(key)
        number = _coerce_number(item)
        if number is not None:
            return abs(number)
    raise UnsupportedProgram("missing extrude distance")


def load_prepared_examples(data_dir: Path, *, split: str = "train") -> list[PreparedCadExample]:
    path = data_dir / f"{split}.jsonl"
    if not path.exists():
        raise ValueError(f"Prepared split does not exist: {path}")
    examples: list[PreparedCadExample] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                examples.append(PreparedCadExample.model_validate_json(line))
    if not examples:
        raise ValueError(f"Prepared split is empty: {path}")
    return examples


def latest_checkpoint(output_dir: Path) -> Path | None:
    checkpoints = sorted(output_dir.glob("checkpoint_step_*.pt"))
    return checkpoints[-1] if checkpoints else None


def train_diffusion_model(
    data_dir: Path,
    output_dir: Path,
    *,
    max_steps: int = 1000,
    batch_size: int = 16,
    max_len: int = 256,
    d_model: int = 128,
    layers: int = 2,
    heads: int = 4,
    learning_rate: float = 3e-4,
    checkpoint_interval: int = 100,
    time_limit_minutes: float = 480.0,
    seed: int = 0,
    resume: bool = True,
    should_stop: Callable[[], bool] | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> TrainSummary:
    try:
        import torch
        from torch import nn
        from torch.nn import functional as F
    except ImportError as exc:
        raise RuntimeError(
            "cad-diffusion training requires PyTorch. Install with `pip install -e .[cad-diffusion]`."
        ) from exc

    random.seed(seed)
    torch.manual_seed(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    examples = load_prepared_examples(data_dir, split="train")
    for example in examples:
        validate_cad_token_grammar(example.tokens, max_len=max_len)
    vocab = CadTokenVocab()
    encoded = [vocab.encode(example.tokens, max_len=max_len) for example in examples]
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = _build_torch_model(nn, len(vocab), max_len, d_model, layers, heads, vocab.pad_id).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    start_step = 0
    checkpoint = latest_checkpoint(output_dir) if resume else None
    if checkpoint is not None:
        payload = torch.load(checkpoint, map_location=device)
        model.load_state_dict(payload["model_state"])
        optimizer.load_state_dict(payload["optimizer_state"])
        start_step = int(payload.get("step", 0))

    started = time.perf_counter()
    deadline = started + (time_limit_minutes * 60)
    step = start_step
    checkpoint_path = checkpoint or (output_dir / "checkpoint_step_000000.pt")
    last_loss: float | None = None
    if on_progress is not None:
        on_progress(
            {
                "phase": "started",
                "step": step,
                "max_steps": max_steps,
                "checkpoint_path": checkpoint_path.as_posix(),
                "device": device,
                "examples": len(examples),
                "loss": last_loss,
                "elapsed_seconds": 0.0,
            }
        )
    while (
        step < max_steps
        and time.perf_counter() < deadline
        and not (should_stop is not None and should_stop())
    ):
        batch = [random.choice(encoded) for _ in range(batch_size)]
        labels = torch.tensor(batch, dtype=torch.long, device=device)
        noise_level = torch.randint(1, 32, (batch_size,), device=device)
        probability = noise_level.float().view(-1, 1) / 32.0
        can_mask = (
            (labels != vocab.pad_id)
            & (labels != vocab.bos_id)
            & (labels != vocab.eos_id)
        )
        mask = (torch.rand(labels.shape, device=device) < probability) & can_mask
        inputs = labels.clone()
        inputs[mask] = vocab.mask_id
        if not bool(mask.any()):
            mask = can_mask
        logits = model(inputs, noise_level)
        loss = F.cross_entropy(logits[mask], labels[mask])
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        step += 1
        last_loss = float(loss.detach().cpu().item())
        if on_progress is not None:
            on_progress(
                {
                    "phase": "training",
                    "step": step,
                    "max_steps": max_steps,
                    "checkpoint_path": checkpoint_path.as_posix(),
                    "device": device,
                    "examples": len(examples),
                    "loss": last_loss,
                    "elapsed_seconds": time.perf_counter() - started,
                }
            )
        if step % checkpoint_interval == 0 or step == max_steps:
            checkpoint_path = save_checkpoint(
                output_dir,
                step=step,
                model=model,
                optimizer=optimizer,
                vocab=vocab,
                max_len=max_len,
                d_model=d_model,
                layers=layers,
                heads=heads,
                loss=last_loss,
            )
            if on_progress is not None:
                on_progress(
                    {
                        "phase": "checkpoint",
                        "step": step,
                        "max_steps": max_steps,
                        "checkpoint_path": checkpoint_path.as_posix(),
                        "device": device,
                        "examples": len(examples),
                        "loss": last_loss,
                        "elapsed_seconds": time.perf_counter() - started,
                    }
                )

    if step != start_step and (not checkpoint_path.exists() or step % checkpoint_interval != 0):
        checkpoint_path = save_checkpoint(
            output_dir,
            step=step,
            model=model,
            optimizer=optimizer,
            vocab=vocab,
            max_len=max_len,
            d_model=d_model,
            layers=layers,
            heads=heads,
            loss=last_loss,
        )
        if on_progress is not None:
            on_progress(
                {
                    "phase": "checkpoint",
                    "step": step,
                    "max_steps": max_steps,
                    "checkpoint_path": checkpoint_path.as_posix(),
                    "device": device,
                    "examples": len(examples),
                    "loss": last_loss,
                    "elapsed_seconds": time.perf_counter() - started,
                }
            )
    if on_progress is not None:
        on_progress(
            {
                "phase": "stopped" if should_stop is not None and should_stop() else "complete",
                "step": step,
                "max_steps": max_steps,
                "checkpoint_path": checkpoint_path.as_posix(),
                "device": device,
                "examples": len(examples),
                "loss": last_loss,
                "elapsed_seconds": time.perf_counter() - started,
            }
        )
    return TrainSummary(
        steps=step,
        checkpoint_path=checkpoint_path,
        device=device,
        examples=len(examples),
        elapsed_seconds=time.perf_counter() - started,
    )


def _build_torch_model(nn: Any, vocab_size: int, max_len: int, d_model: int, layers: int, heads: int, pad_id: int):
    class CadDenoiser(nn.Module):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            super().__init__()
            self.token_embedding = nn.Embedding(vocab_size, d_model, padding_idx=pad_id)
            self.position_embedding = nn.Embedding(max_len, d_model)
            self.noise_embedding = nn.Embedding(32, d_model)
            layer = nn.TransformerEncoderLayer(
                d_model=d_model,
                nhead=heads,
                dim_feedforward=d_model * 4,
                dropout=0.1,
                activation="gelu",
                batch_first=True,
            )
            self.encoder = nn.TransformerEncoder(layer, num_layers=layers)
            self.output = nn.Linear(d_model, vocab_size)

        def forward(self, ids: Any, noise_level: Any) -> Any:
            import torch

            positions = torch.arange(ids.shape[1], device=ids.device).unsqueeze(0)
            x = (
                self.token_embedding(ids)
                + self.position_embedding(positions)
                + self.noise_embedding(noise_level.clamp(0, 31)).unsqueeze(1)
            )
            padding_mask = ids == pad_id
            return self.output(self.encoder(x, src_key_padding_mask=padding_mask))

    return CadDenoiser()


def save_checkpoint(
    output_dir: Path,
    *,
    step: int,
    model: Any,
    optimizer: Any,
    vocab: CadTokenVocab,
    max_len: int,
    d_model: int,
    layers: int,
    heads: int,
    loss: float | None,
) -> Path:
    import torch

    path = output_dir / f"checkpoint_step_{step:06d}.pt"
    payload = {
        "step": step,
        "vocab": vocab.tokens,
        "max_len": max_len,
        "model_config": {"d_model": d_model, "layers": layers, "heads": heads},
        "model_state": model.state_dict(),
        "optimizer_state": optimizer.state_dict(),
        "loss": loss,
        "saved_at_utc": timestamp_utc(),
    }
    torch.save(payload, path)
    return path


def sample_diffusion_model(
    checkpoint_path: Path,
    run_dir: Path,
    *,
    count: int = 100,
    denoise_steps: int = 16,
    temperature: float = 1.0,
    seed: int = 0,
    data_dir: Path | None = None,
) -> list[CadDiffusionRecord]:
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "cad-diffusion sampling requires PyTorch. Install with `pip install -e .[cad-diffusion]`."
        ) from exc
    if not checkpoint_path.exists():
        raise ValueError(f"Checkpoint does not exist: {checkpoint_path}")

    payload = torch.load(checkpoint_path, map_location="cpu")
    vocab = CadTokenVocab(list(payload["vocab"]))
    max_len = int(payload["max_len"])
    config = payload["model_config"]
    device = "cuda" if torch.cuda.is_available() else "cpu"
    from torch import nn

    model = _build_torch_model(
        nn,
        len(vocab),
        max_len,
        int(config["d_model"]),
        int(config["layers"]),
        int(config["heads"]),
        vocab.pad_id,
    ).to(device)
    model.load_state_dict(payload["model_state"])
    model.eval()

    training_tokens = load_training_tokens(data_dir) if data_dir is not None and data_dir.exists() else []
    run_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = run_dir / "results.jsonl"
    records: list[CadDiffusionRecord] = []
    generator = torch.Generator(device=device).manual_seed(seed)
    allowed_ids = torch.tensor(vocab.sample_allowed_ids(), dtype=torch.long, device=device)
    experiment_id = run_dir.name

    with jsonl_path.open("a", encoding="utf-8") as handle:
        for index in range(count):
            started = time.perf_counter()
            sample_seed = seed + index
            ids = torch.full((1, max_len), vocab.mask_id, dtype=torch.long, device=device)
            ids[0, 0] = vocab.bos_id
            for step in reversed(range(denoise_steps)):
                noise_level = torch.full((1,), min(31, step + 1), dtype=torch.long, device=device)
                with torch.no_grad():
                    logits = model(ids, noise_level) / max(temperature, 1e-6)
                logits[:, :, [vocab.pad_id, vocab.bos_id, vocab.mask_id, vocab.unk_id]] = -1e9
                probs = torch.softmax(logits, dim=-1)
                sampled = torch.multinomial(
                    probs.reshape(-1, probs.shape[-1]),
                    num_samples=1,
                    generator=generator,
                ).reshape(1, max_len)
                fill = ids == vocab.mask_id
                ids[fill] = sampled[fill]
                if step > 0:
                    keep_probability = 1.0 - (step / denoise_steps)
                    mutable = torch.ones_like(ids, dtype=torch.bool)
                    mutable[0, 0] = False
                    mutable &= ids != vocab.eos_id
                    remask = (
                        torch.rand(ids.shape, device=device, generator=generator) > keep_probability
                    ) & mutable
                    ids[remask] = vocab.mask_id
            tokens = vocab.decode(ids[0].detach().cpu().tolist())
            artifacts: dict[str, str] = {}
            program_payload: dict[str, Any] | None = None
            parse_error: str | None = None
            compile_error: str | None = None
            render_error: str | None = None
            metrics: dict[str, float | int | str | None] = {}
            sample_id = str(uuid4())
            artifact_dir = run_dir / "artifacts" / sample_id[:8]
            artifact_dir.mkdir(parents=True, exist_ok=True)
            (artifact_dir / "tokens.txt").write_text(" ".join(tokens) + "\n", encoding="utf-8")
            try:
                program = tokens_to_program(tokens)
                program_payload = program.model_dump(mode="json")
                metrics = program_metrics(program)
            except Exception as exc:  # noqa: BLE001 - recorded as parse failure.
                parse_error = str(exc)
            if program_payload is not None:
                try:
                    artifacts, render_error = compile_program_artifacts(program, artifact_dir)
                except Exception as exc:  # noqa: BLE001 - recorded as compile failure.
                    compile_error = str(exc)
            record = CadDiffusionRecord(
                sample_id=sample_id,
                experiment_id=experiment_id,
                timestamp_utc=timestamp_utc(),
                checkpoint_path=checkpoint_path.as_posix(),
                seed=sample_seed,
                tokens=tokens,
                program=program_payload,
                parse_error=parse_error,
                compile_error=compile_error,
                render_error=render_error,
                artifacts=artifacts,
                metrics=metrics,
                nearest_neighbor_distance=nearest_neighbor_distance(tokens, training_tokens),
                elapsed_ms=int((time.perf_counter() - started) * 1000),
            )
            handle.write(record.model_dump_json() + "\n")
            handle.flush()
            records.append(record)
    return records


def load_training_tokens(data_dir: Path) -> list[list[str]]:
    try:
        return [example.tokens for example in load_prepared_examples(data_dir, split="train")]
    except ValueError:
        return []


def nearest_neighbor_distance(tokens: list[str], candidates: list[list[str]]) -> float | None:
    if not candidates:
        return None
    return min(normalized_edit_distance(tokens, candidate) for candidate in candidates)


def normalized_edit_distance(left: list[str], right: list[str]) -> float:
    if not left and not right:
        return 0.0
    previous = list(range(len(right) + 1))
    for i, left_token in enumerate(left, start=1):
        current = [i]
        for j, right_token in enumerate(right, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (0 if left_token == right_token else 1),
                )
            )
        previous = current
    return previous[-1] / max(len(left), len(right), 1)


def eval_cad_diffusion_run(run_dir: Path) -> EvalSummary:
    path = run_dir / "results.jsonl"
    if not path.exists():
        raise ValueError(f"Run results do not exist: {path}")
    records: list[CadDiffusionRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(CadDiffusionRecord.model_validate_json(line))
    unique_tokens = {" ".join(record.tokens) for record in records}
    unique_programs = {
        json.dumps(record.program, sort_keys=True)
        for record in records
        if record.program is not None
    }
    distances = [
        record.nearest_neighbor_distance
        for record in records
        if record.nearest_neighbor_distance is not None
    ]
    return EvalSummary(
        total=len(records),
        parse_valid=sum(1 for record in records if record.parse_error is None),
        compiled=sum(1 for record in records if record.compile_error is None and record.program is not None),
        renderable=sum(
            1
            for record in records
            if record.parse_error is None
            and record.compile_error is None
            and record.render_error is None
            and bool(record.artifacts.get("stl"))
        ),
        unique_token_sequences=len(unique_tokens),
        unique_programs=len(unique_programs),
        mean_nearest_neighbor_distance=(
            sum(distances) / len(distances) if distances else None
        ),
    )
