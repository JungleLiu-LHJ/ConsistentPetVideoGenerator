"""File system helpers shared across the pipeline."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def ensure_dir(path: str | Path) -> Path:
    """Create the directory if it does not exist."""
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def read_binary(path: str | Path) -> bytes:
    """Read binary content from a file."""
    with open(path, "rb") as handle:
        return handle.read()


def write_text(path: str | Path, content: str) -> Path:
    """Write UTF-8 text to disk."""
    target = Path(path)
    ensure_dir(target.parent)
    target.write_text(content, encoding="utf-8")
    return target


def write_json(path: str | Path, data: Any) -> Path:
    """Serialize a Python object as JSON to disk."""
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    return write_text(path, payload)


def sha256_hex(data: bytes) -> str:
    """Return the hexadecimal SHA-256 digest for the given bytes."""
    return hashlib.sha256(data).hexdigest()


def b64encode(data: bytes) -> str:
    """Encode bytes to a base64 string without newlines."""
    return base64.b64encode(data).decode("utf-8")


def b64decode_to_bytes(data: str) -> bytes:
    """Decode a base64 string into bytes."""
    return base64.b64decode(data.encode("utf-8"))


def guess_extension(path: str | Path) -> str | None:
    """Extract the file extension (without leading dot)."""
    suffix = Path(path).suffix
    return suffix[1:].lower() if suffix else None


def atomic_write(path: str | Path, content: bytes) -> Path:
    """Write binary content to disk atomically."""
    target = Path(path)
    ensure_dir(target.parent)
    temp_path = target.with_suffix(target.suffix + ".tmp")
    with open(temp_path, "wb") as handle:
        handle.write(content)
    os.replace(temp_path, target)
    return target
