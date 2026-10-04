"""Small shared helpers for the app's local JSON persistence."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def atomic_write_json(path: Path, data: dict) -> None:
    """Writes via a temp file + os.replace so a crash or power loss mid-save
    can never leave a half-written, corrupted file - the rename is atomic,
    so readers always see either the old file or the fully-new one.
    """
    path.parent.mkdir(exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(data, indent=2))
        os.replace(tmp_path, path)
    except BaseException:
        os.unlink(tmp_path)
        raise
