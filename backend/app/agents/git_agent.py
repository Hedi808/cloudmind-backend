import os
import re
import shutil
import stat
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from git import GitCommandError, Repo

from app.core.config import settings


class GitAgent:
    """
    Controlled Git agent for CloudMind.

    Responsibilities:
    - clone repository with write authentication
    - pull latest repository changes
    - create a safe deployment branch
    - commit generated deployment files
    - push branch to GitHub
    - open a pull request
    """

    def __init__(self):
        self.github_token = settings.github_token
        self.github_username = settings.github_username

    def clone_for_write(
        self,
        repo_url: str,
        local_repo_path: str,
        branch: str | None = None,
    ) -> dict[str, Any]:
        """
        Clone a GitHub repository using token authentication.
        This supports private repositories selected in the fine-grained token.
        """
        if not self.github_token:
            raise RuntimeError("GITHUB_TOKEN is missing in .env")

        repo_path = Path(local_repo_path)

        if repo_path.exists():
            self._safe_delete_folder(repo_path)

        repo_path.parent.mkdir(parents=True, exist_ok=True)

        public_url = self._normalize_repo_url(repo_url)
        authenticated_url = self._build_authenticated_url(public_url)

        try:
            clone_kwargs = {
                "multi_options": ["--depth=1"],
            }

            if branch:
                clone_kwargs["branch"] = branch

            repo = Repo.clone_from(authenticated_url, repo_path, **clone_kwargs)

            # Important: restore clean public origin URL so token is not stored in .git/config
            repo.remote(name="origin").set_url(public_url)

            return {
                "status": "cloned",
                "local_path": str(repo_path),
                "branch": branch or repo.active_branch.name,
            }

        except GitCommandError as exc:
            raise RuntimeError(f"Failed to clone repository for write: {exc}") from exc

    def pull_latest(self, local_repo_path: str, branch: str | None = None) -> dict[str, Any]:
        repo_path = Path(local_repo_path)

        if not repo_path.exists():
            raise FileNotFoundError(f"Repository path not found: {repo_path}")

        repo = Repo(repo_path)

        if repo.bare:
            raise RuntimeError("Repository is bare and cannot be used for working tree operations.")

        origin = repo.remote(name="origin")

        if branch:
            self._checkout_branch(repo, branch)

        try:
            pull_result = origin.pull()
        except GitCommandError as exc:
            raise RuntimeError(f"Failed to pull latest changes: {exc}") from exc

        return {
            "status": "pulled",
            "branch": repo.active_branch.name,
            "result": [str(item) for item in pull_result],
        }

    def create_branch(self, local_repo_path: str, branch_name: str) -> dict[str, Any]:
        repo = Repo(Path(local_repo_path))
        safe_branch_name = self._sanitize_branch_name(branch_name)

        existing_branches = [head.name for head in repo.heads]

        if safe_branch_name in existing_branches:
            repo.git.checkout(safe_branch_name)
        else:
            repo.git.checkout("-b", safe_branch_name)

        return {
            "status": "branch_ready",
            "branch": safe_branch_name,
        }

    def commit_changes(
        self,
        local_repo_path: str,
        commit_message: str,
        files_to_add: list[str] | None = None,
    ) -> dict[str, Any]:
        repo_path = Path(local_repo_path)
        repo = Repo(repo_path)

        self._ensure_git_identity(repo)

        if files_to_add:
            for file_path in files_to_add:
                repo.git.add(file_path)
        else:
            repo.git.add(A=True)

        if not repo.is_dirty(untracked_files=True):
            return {
                "status": "no_changes",
                "message": "No changes to commit.",
            }

        commit = repo.index.commit(commit_message)

        return {
            "status": "committed",
            "commit": commit.hexsha,
            "message": commit_message,
        }

    def push_branch(
        self,
        local_repo_path: str,
        branch_name: str,
        repo_url: str,
    ) -> dict[str, Any]:
        if not self.github_token:
            raise RuntimeError("GITHUB_TOKEN is missing in .env")

        repo = Repo(Path(local_repo_path))
        safe_branch_name = self._sanitize_branch_name(branch_name)

        public_url = self._normalize_repo_url(repo_url)
        authenticated_url = self._build_authenticated_url(public_url)

        origin = repo.remote(name="origin")
        original_url = origin.url

        try:
            origin.set_url(authenticated_url)

            push_result = repo.git.push(
                "--set-upstream",
                "origin",
                safe_branch_name,
            )

            return {
                "status": "pushed",
                "branch": safe_branch_name,
                "result": push_result,
            }

        except GitCommandError as exc:
            raise RuntimeError(f"Failed to push branch: {exc}") from exc

        finally:
            # Important: never keep the token in .git/config
            origin.set_url(original_url or public_url)

    def open_pull_request(
        self,
        repo_url: str,
        branch_name: str,
        title: str,
        body: str,
        base_branch: str = "main",
    ) -> dict[str, Any]:
        if not self.github_token:
            raise RuntimeError("GITHUB_TOKEN is missing in .env")

        owner, repo_name = self._parse_github_owner_repo(repo_url)

        api_url = f"https://api.github.com/repos/{owner}/{repo_name}/pulls"

        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        payload = {
            "title": title,
            "head": branch_name,
            "base": base_branch,
            "body": body,
        }

        response = requests.post(api_url, headers=headers, json=payload, timeout=30)

        if response.status_code not in [200, 201]:
            raise RuntimeError(
                f"Failed to open pull request: {response.status_code} {response.text}"
            )

        data = response.json()

        return {
            "status": "pull_request_created",
            "number": data.get("number"),
            "url": data.get("html_url"),
            "title": data.get("title"),
        }

    def publish_deployment_changes(
        self,
        local_repo_path: str,
        repo_url: str,
        generated_files: list[str] | None = None,
        base_branch: str = "main",
        branch_name: str = "cloudmind/deployment-files",
    ) -> dict[str, Any]:
        """
        Safe publishing flow:
        1. pull latest base branch
        2. create CloudMind branch
        3. commit generated files
        4. push branch
        5. open pull request
        """
        safe_branch_name = self._sanitize_branch_name(branch_name)

        self.pull_latest(local_repo_path=local_repo_path, branch=base_branch)

        branch_result = self.create_branch(
            local_repo_path=local_repo_path,
            branch_name=safe_branch_name,
        )

        commit_result = self.commit_changes(
            local_repo_path=local_repo_path,
            commit_message="chore: add CloudMind deployment files",
            files_to_add=generated_files,
        )

        if commit_result["status"] == "no_changes":
            return {
                "status": "no_changes",
                "message": "No deployment changes were found to publish.",
                "branch": branch_result,
            }

        push_result = self.push_branch(
            local_repo_path=local_repo_path,
            branch_name=safe_branch_name,
            repo_url=repo_url,
        )

        pr_result = self.open_pull_request(
            repo_url=repo_url,
            branch_name=safe_branch_name,
            title="Add CloudMind deployment files",
            body=(
                "This pull request was generated by CloudMind.\n\n"
                "It contains deployment-related files generated from repository analysis."
            ),
            base_branch=base_branch,
        )

        return {
            "status": "published",
            "branch": safe_branch_name,
            "commit": commit_result,
            "push": push_result,
            "pull_request": pr_result,
        }

    def _checkout_branch(self, repo: Repo, branch: str) -> None:
        local_branches = [head.name for head in repo.heads]

        if branch in local_branches:
            repo.git.checkout(branch)
            return

        remote_branch = f"origin/{branch}"
        remote_refs = [ref.name for ref in repo.remote().refs]

        if remote_branch in remote_refs:
            repo.git.checkout("-b", branch, "--track", remote_branch)
            return

        raise RuntimeError(f"Branch '{branch}' was not found locally or on origin.")

    def _build_authenticated_url(self, repo_url: str) -> str:
        """
        Converts:
        https://github.com/owner/repo.git

        Into:
        https://x-access-token:TOKEN@github.com/owner/repo.git

        Never print or log this URL.
        """
        if not self.github_token:
            raise RuntimeError("GITHUB_TOKEN is missing in .env")

        parsed = urlparse(repo_url)

        if parsed.scheme != "https":
            raise ValueError("Only HTTPS GitHub repository URLs are supported for token auth.")

        return f"https://x-access-token:{self.github_token}@{parsed.netloc}{parsed.path}"

    def _normalize_repo_url(self, repo_url: str) -> str:
        repo_url = repo_url.strip()

        if repo_url.endswith(".git"):
            return repo_url

        return repo_url + ".git"

    def _parse_github_owner_repo(self, repo_url: str) -> tuple[str, str]:
        parsed = urlparse(repo_url)
        parts = parsed.path.strip("/").split("/")

        if len(parts) < 2:
            raise ValueError("Invalid GitHub repository URL.")

        owner = parts[0]
        repo_name = parts[1]

        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]

        return owner, repo_name

    def _sanitize_branch_name(self, branch_name: str) -> str:
        branch_name = branch_name.strip().replace(" ", "-")
        branch_name = re.sub(r"[^a-zA-Z0-9/_-]", "", branch_name)

        if not branch_name:
            branch_name = "cloudmind/deployment-files"

        return branch_name

    def _ensure_git_identity(self, repo: Repo) -> None:
        """
        Ensures Git has a local user.name and user.email before committing.
        This avoids commit failures on fresh machines.
        """
        username = self.github_username or "cloudmind-bot"

        repo.git.config("user.name", username)
        repo.git.config("user.email", f"{username}@users.noreply.github.com")

    def _safe_delete_folder(self, folder_path: Path) -> None:
        """
        Deletes an existing cloned repository folder.
        Handles Windows read-only Git files.
        """

        def remove_readonly(func, path, exc_info):
            os.chmod(path, stat.S_IWRITE)
            func(path)

        for attempt in range(3):
            try:
                shutil.rmtree(folder_path, onexc=remove_readonly)
                return
            except TypeError:
                shutil.rmtree(folder_path, onerror=remove_readonly)
                return
            except PermissionError:
                if attempt == 2:
                    raise
                time.sleep(1)