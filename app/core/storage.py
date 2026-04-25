import asyncio
import re
import shutil
from pathlib import Path

# Base directory: auth-service/app/db/mri_scans/
MRI_SCANS_DIR = Path(__file__).parent.parent / "db" / "mri_scans"


async def save_scan_locally(
    file_bytes: bytes,
    case_id: str,
    filename: str,
) -> str:
    """
    Save MRI scan bytes to disk at app/db/mri_scans/{case_id}/{filename}.
    Returns the path relative to the auth-service root.
    """
    case_dir = MRI_SCANS_DIR / case_id

    def _write() -> None:
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / filename).write_bytes(file_bytes)

    await asyncio.to_thread(_write)
    return f"app/db/mri_scans/{case_id}/{filename}"


async def save_scan_to_session(
    file_bytes: bytes,
    session_id: str,
    file_index: int,
    filename: str,
) -> None:
    """Save a single scan to a temporary session directory for parallel uploads."""
    safe_name = re.sub(r"[^\w.\-]", "_", Path(filename).name)
    session_dir = MRI_SCANS_DIR / f"_session_{session_id}"

    def _write() -> None:
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / f"{file_index}_{safe_name}").write_bytes(file_bytes)

    await asyncio.to_thread(_write)


async def move_session_to_case(session_id: str, case_id: str) -> list[str]:
    """Move session files to permanent case directory. Returns sorted scan paths."""
    session_dir = MRI_SCANS_DIR / f"_session_{session_id}"
    case_dir = MRI_SCANS_DIR / case_id

    def _move() -> list[str]:
        if not session_dir.exists():
            return []
        case_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for f in sorted(session_dir.iterdir()):
            # filename format: "{index}_{original_name}"
            idx_str, _, orig = f.name.partition("_")
            dot = orig.find(".")
            ext = orig[dot:] if dot != -1 else ""
            dest = case_dir / f"scan_{idx_str}{ext}"
            shutil.move(str(f), str(dest))
            paths.append(f"app/db/mri_scans/{case_id}/scan_{idx_str}{ext}")
        shutil.rmtree(str(session_dir), ignore_errors=True)
        return sorted(paths)

    return await asyncio.to_thread(_move)


async def delete_scan_dir(case_id: str) -> None:
    """Remove the scan directory for a case, if it exists."""
    case_dir = MRI_SCANS_DIR / case_id

    def _remove() -> None:
        if case_dir.exists():
            shutil.rmtree(case_dir)

    await asyncio.to_thread(_remove)
