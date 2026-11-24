"""Build the export document and write it to disk safely."""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from models.schemas import AnalysisResult

FILENAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,60}_leetcode_data\.json$")


class JSONGenerationError(Exception):
    pass


def safe_filename(username: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]", "_", username).strip("._") or "profile"
    return f"{stem[:60]}_leetcode_data.json"


def to_json_text(document: AnalysisResult) -> str:
    return json.dumps(document.model_dump(mode="json"), ensure_ascii=False, indent=2)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)  # atomic on Windows and POSIX
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def write_document(document: AnalysisResult, output_dir: Path, raw: dict[str, Any] | None = None) -> str:
    """Write <username>_leetcode_data.json (and raw/<username>_raw.json); return the filename."""
    filename = safe_filename(document.profile.username)
    path = Path(output_dir) / filename
    try:
        text = to_json_text(document)
        _atomic_write(path, text)
        # Read back and re-validate so a corrupt file is never offered for download.
        AnalysisResult.model_validate(json.loads(path.read_text(encoding="utf-8")))
        if raw is not None:
            raw_name = filename.replace("_leetcode_data.json", "_raw.json")
            _atomic_write(Path(output_dir) / "raw" / raw_name, json.dumps(raw, ensure_ascii=False, indent=2))
    except (OSError, ValueError, TypeError) as exc:
        raise JSONGenerationError(f"Could not write the JSON file: {exc}") from exc
    return filename


def resolve_download(output_dir: Path, filename: str) -> Path | None:
    """Return the path for a download request, or None if the name is not one we produce."""
    if not FILENAME_RE.match(filename):
        return None
    base = Path(output_dir).resolve()
    path = (base / filename).resolve()
    if path.parent != base or not path.is_file():
        return None
    return path
