from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from flask import current_app


class OutputNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class OutputFile:
    job_id: str
    path: Path
    mimetype: str
    download_name: str


def _outputs_dir() -> Path:
    instance_path = Path(current_app.instance_path)
    out_dir = instance_path / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def save_output_bytes(payload: bytes, *, download_name: str, mimetype: str) -> str:
    job_id = uuid.uuid4().hex
    out_dir = _outputs_dir()
    file_path = out_dir / job_id
    file_path.write_bytes(payload)

    meta_path = out_dir / f"{job_id}.meta"
    meta_path.write_text(f"{mimetype}\n{download_name}\n", encoding="utf-8")
    return job_id


def get_output_file(job_id: str) -> OutputFile:
    out_dir = _outputs_dir()
    file_path = (out_dir / job_id).resolve()
    meta_path = (out_dir / f"{job_id}.meta").resolve()

    if file_path.parent != out_dir.resolve() or meta_path.parent != out_dir.resolve():
        raise OutputNotFoundError("Invalid job id.")
    if not file_path.exists() or not meta_path.exists():
        raise OutputNotFoundError("Missing output.")

    meta = meta_path.read_text(encoding="utf-8").splitlines()
    if len(meta) < 2:
        raise OutputNotFoundError("Corrupted output metadata.")
    mimetype, download_name = meta[0].strip(), meta[1].strip()
    if not mimetype or not download_name:
        raise OutputNotFoundError("Corrupted output metadata.")

    return OutputFile(job_id=job_id, path=file_path, mimetype=mimetype, download_name=os.path.basename(download_name))

