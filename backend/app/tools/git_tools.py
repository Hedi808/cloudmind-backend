import os
import re
import shutil
import stat
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from git import GitCommandError, Repo


WORKSPACE_DIR = Path("workspace/repos")


def sanitize_repo_name(repo_url: str) -> str:
    """
    Converts a repo URL into a safe folder/repo name.
    Example:
    https://github.com/user/my-app.git -> my-app
    """
    parsed = urlparse(repo_url)
    name = Path(parsed.path).name

    if name.endswith(".git"):
        name = name[:-4]

    name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)

    if not name:
        name = "repository"

    return name


def _remove_readonly(func, path, exc_info):
    """
    Windows fix:
    If Git creates read-only files, make them writable and retry deletion.
    """
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        raise


def safe_rmtree(path: Path) -> None:
    """
    Safely delete a folder on Windows, including Git folders.
    This is best-effort. If Windows locks a folder, callers may decide to ignore it.
    """
    if not path.exists():
        return

    for attempt in range(3):
        try:
            shutil.rmtree(path, onexc=_remove_readonly)
            return
        except TypeError:
            shutil.rmtree(path, onerror=_remove_readonly)
            return
        except PermissionError:
            if attempt == 2:
                raise
            time.sleep(1)


def _unique_clone_path(repo_name: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return WORKSPACE_DIR / f"{repo_name}-{timestamp}-{suffix}"


def _cleanup_old_repo_clones(repo_name: str, keep_latest: int = 5) -> None:
    """
    Best-effort cleanup only.

    Important:
    - Never block the pipeline if Windows locks a previous clone.
    - Never reuse/delete the active target clone.
    """
    if not WORKSPACE_DIR.exists():
        return

    candidates = [
        path
        for path in WORKSPACE_DIR.iterdir()
        if path.is_dir()
        and (
            path.name == repo_name
            or path.name.startswith(f"{repo_name}-")
        )
    ]

    candidates = sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)

    for old_path in candidates[keep_latest:]:
        try:
            safe_rmtree(old_path)
        except Exception:
            # Windows/OneDrive/antivirus may lock old clones.
            # Ignore cleanup failures because every new clone uses a unique folder.
            continue


def clone_repository(repo_url: str, branch: str | None = None) -> Path:
    """
    Clone a public Git repository into a unique temporary workspace folder.

    Phase 20D change:
    - No more reusable workspace/repos/<repo-name> folder.
    - No more deleting the same folder before every run.
    - This avoids Windows [WinError 32] file lock failures.
    """
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    repo_name = sanitize_repo_name(repo_url)
    target_path = _unique_clone_path(repo_name)

    try:
        clone_kwargs = {
            "multi_options": ["--depth=1"],
        }

        if branch:
            clone_kwargs["branch"] = branch

        Repo.clone_from(repo_url, target_path, **clone_kwargs)

        _cleanup_old_repo_clones(repo_name=repo_name, keep_latest=5)

        return target_path

    except GitCommandError as exc:
        raise RuntimeError(f"Failed to clone repository: {exc}") from exc