"""Byte-reproducible archive builder for generation request/response artifacts."""

from __future__ import annotations

import hashlib
from pathlib import Path
import zipfile


ARCHIVE_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ARCHIVE_MODE = 0o100644


def build_deterministic_archive(
    output: str | Path,
    files: dict[str, bytes | str],
) -> str:
    """Write a canonical ZIP and return its SHA-256 digest.

    Entry names are normalized relative POSIX paths; order, timestamp, mode and
    compression settings are fixed. Unsafe or duplicate normalized names fail.
    """
    normalized: dict[str, bytes] = {}
    for raw_name, value in files.items():
        name = raw_name.replace("\\", "/").lstrip("/")
        if not name or name.startswith("../") or "/../" in name or name in normalized:
            raise ValueError(f"unsafe or duplicate archive entry: {raw_name!r}")
        normalized[name] = value.encode("utf-8") if isinstance(value, str) else bytes(value)
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(normalized):
            info = zipfile.ZipInfo(name, ARCHIVE_TIMESTAMP)
            info.create_system = 3
            info.external_attr = ARCHIVE_MODE << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, normalized[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return hashlib.sha256(path.read_bytes()).hexdigest()
