"""Resolve historical paths for offline analysis without rewriting provenance."""
from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath


def resolve_recorded_path(path: str | Path, recorded_run_dir: str | Path | None,
                          actual_run_dir: str | Path) -> Path:
    """Keep a recorded path's layout relative to the run supplied by the caller.

    Frozen manifests contain absolute paths from the collection machine. Treat
    those as provenance, never as an existence-based fallback to another copy.
    Windows paths are parsed on every OS. A relocated release must retain the
    original relative layout, including the ledger and predecessor runs.
    Relative paths, if supplied, are relative to the current manifest directory.
    """
    value = str(path)
    flavor = PureWindowsPath if PureWindowsPath(value).drive or "\\" in value else PurePosixPath
    target = flavor(value)
    actual = Path(actual_run_dir).resolve()
    if not target.is_absolute():
        if target.drive or target.root:
            raise ValueError("Recorded path must be absolute or manifest-relative.")
        return actual.joinpath(*target.parts).resolve()
    if recorded_run_dir is None:
        raise ValueError("An absolute recorded path requires its frozen run_dir for offline relocation.")
    origin = flavor(str(recorded_run_dir))
    if not origin.is_absolute() or flavor(origin.anchor) != flavor(target.anchor):
        raise ValueError("Recorded path and frozen run_dir must share an absolute filesystem root.")
    common = 0
    for left, right in zip(origin.parts, target.parts):
        if flavor(left) != flavor(right):
            break
        common += 1
    if common <= 1:
        raise ValueError("Recorded path and frozen run_dir have no shared directory layout.")
    return actual.joinpath(*([".."] * (len(origin.parts) - common)),
                           *target.parts[common:]).resolve()
