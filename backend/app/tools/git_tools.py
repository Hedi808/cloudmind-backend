import os
import re
import shutil
import stat
import time
from pathlib import Path
from urllib.parse import urlparse

from git import Repo, GitCommandError


WORKSPACE_DIR = Path("workspace/repos")


def sanitize_repo_name(repo_url: str) -> str:
    """
    Converts a repo URL into a safe local folder name.
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
    """
    if not path.exists():
        return

    # Small retry loop because Windows/OneDrive/antivirus can temporarily lock files
    for attempt in range(3):
        try:
            shutil.rmtree(path, onexc=_remove_readonly)
            return
        except TypeError:
            # Fallback for older Python versions that use onerror instead of onexc
            shutil.rmtree(path, onerror=_remove_readonly)
            return
        except PermissionError:
            if attempt == 2:
                raise
            time.sleep(1)


def clone_repository(repo_url: str, branch: str | None = None) -> Path:
    """
    Clone a public Git repository into workspace/repos.
    Existing copy is deleted to ensure a fresh analysis.
    """
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    repo_name = sanitize_repo_name(repo_url)
    target_path = WORKSPACE_DIR / repo_name

    if target_path.exists():
        safe_rmtree(target_path)

    try:
        clone_kwargs = {
            "multi_options": ["--depth=1"]
        }

        if branch:
            clone_kwargs["branch"] = branch

        Repo.clone_from(repo_url, target_path, **clone_kwargs)
        return target_path

    except GitCommandError as exc:
        raise RuntimeError(f"Failed to clone repository: {exc}") from exc