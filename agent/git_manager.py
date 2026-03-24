"""
Git operations manager - handles cloning, branching, committing, pushing, and MR creation.
Uses GitPython for local operations and GitLab API for merge requests.
"""

import os
import subprocess
from datetime import datetime
from typing import Optional

import httpx
from git import Repo, GitCommandError
from loguru import logger

from config import Config


class GitManager:
    """Manages all Git operations for the auto-fix agent."""

    def __init__(self, config: Config, repo_path: Optional[str] = None):
        """
        Initialize Git manager.

        Args:
            config: Configuration object
            repo_path: Path to local repository (will clone if doesn't exist)
        """
        self.config = config
        self.repo_path = repo_path or config.repo_path or "./git_clones/repo"
        self.repo: Optional[Repo] = None

        self.base_url = f"{config.gitlab_url}/api/v4"
        self.headers = {
            "PRIVATE-TOKEN": config.gitlab_token,
            "Content-Type": "application/json"
        }

        self._ensure_repo()

    def _ensure_repo(self) -> None:
        """Ensure repository exists locally, clone if necessary."""
        if os.path.exists(os.path.join(self.repo_path, ".git")):
            logger.info(f"[GIT] Using existing repository at {self.repo_path}")
            try:
                self.repo = Repo(self.repo_path)
            except Exception as e:
                logger.error(f"[GIT] Failed to open repository: {e}")
                print(
                    f"\n[MANUAL ACTION REQUIRED] Repository at {self.repo_path} is corrupted.\n"
                    f"Please fix it manually or delete the directory and let the agent re-clone.\n"
                )
                raise
        else:
            logger.info(f"[GIT] Repository not found at {self.repo_path}")
            print(
                f"\n[MANUAL ACTION REQUIRED] Repository needs to be cloned.\n"
                f"The agent will attempt to clone it, but if this fails,\n"
                f"please clone it manually to: {self.repo_path}\n\n"
                f"Attempting auto-clone...\n"
            )
            self._clone_repo()

    def _clone_repo(self) -> None:
        """Clone the repository from GitLab."""
        try:
            # Get project details to construct clone URL
            project_url = f"{self.base_url}/projects/{self.config.gitlab_project_id}"

            with httpx.Client(timeout=30.0) as client:
                response = client.get(project_url, headers=self.headers)
                response.raise_for_status()
                project_data = response.json()

            # Construct authenticated clone URL
            http_url = project_data.get("http_url_to_repo", "")

            if not http_url:
                raise ValueError("Could not get repository clone URL from GitLab")

            # Insert token into URL for authentication
            authenticated_url = http_url.replace(
                "https://",
                f"https://oauth2:{self.config.gitlab_token}@"
            )

            # Create parent directory if needed
            os.makedirs(os.path.dirname(self.repo_path), exist_ok=True)

            # Clone
            logger.info(f"[GIT] Cloning repository to {self.repo_path}")
            self.repo = Repo.clone_from(authenticated_url, self.repo_path)

            logger.info("[GIT] Repository cloned successfully")

        except Exception as e:
            logger.error(f"[GIT] Failed to clone repository: {e}")
            print(
                f"\n[MANUAL ACTION REQUIRED] Auto-clone failed.\n"
                f"Please clone your repository manually to: {self.repo_path}\n"
                f"Error: {e}\n"
            )
            raise

    def create_fix_branch(self, job_id: str) -> str:
        """
        Create and checkout a new fix branch.

        Args:
            job_id: GitLab job ID

        Returns:
            Branch name
        """
        # Fetch latest changes first
        try:
            logger.info("[GIT] Fetching latest changes from remote")
            self.repo.remotes.origin.fetch()
        except GitCommandError as e:
            logger.warning(f"[GIT] Failed to fetch from remote: {e}")

        # Create branch name with timestamp
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        branch_name = f"auto-fix/job-{job_id}-{timestamp}"

        try:
            # Checkout default branch first
            default_branch = self.config.gitlab_default_branch
            self.repo.git.checkout(default_branch)

            # Pull latest changes
            self.repo.remotes.origin.pull(default_branch)

            # Create and checkout new branch
            new_branch = self.repo.create_head(branch_name)
            new_branch.checkout()

            logger.info(f"[GIT] Created and checked out branch: {branch_name}")
            return branch_name

        except GitCommandError as e:
            logger.error(f"[GIT] Failed to create branch: {e}")
            raise

    def commit_fix(
        self,
        file_modified: str,
        error_type: str,
        job_id: str,
        pipeline_id: str,
        package_name: Optional[str] = None
    ) -> str:
        """
        Commit the fix to the current branch.

        Args:
            file_modified: Path to modified file
            error_type: Type of error fixed
            job_id: GitLab job ID
            pipeline_id: GitLab pipeline ID
            package_name: Package name for dependency fixes

        Returns:
            Commit SHA
        """
        try:
            # Get relative path from repo root
            if os.path.isabs(file_modified):
                rel_path = os.path.relpath(file_modified, self.repo_path)
            else:
                rel_path = file_modified

            # Stage only the modified file
            self.repo.index.add([rel_path])

            # Create detailed commit message
            commit_message = self._create_commit_message(
                error_type, rel_path, job_id, pipeline_id, package_name
            )

            # Commit
            commit = self.repo.index.commit(commit_message)

            logger.info(f"[GIT] Committed fix: {commit.hexsha[:8]}")
            return commit.hexsha

        except GitCommandError as e:
            logger.error(f"[GIT] Failed to commit: {e}")
            raise

    def _create_commit_message(
        self,
        error_type: str,
        file_path: str,
        job_id: str,
        pipeline_id: str,
        package_name: Optional[str] = None
    ) -> str:
        """
        Create a structured commit message.

        Args:
            error_type: Type of error
            file_path: File that was modified
            job_id: Job ID
            pipeline_id: Pipeline ID
            package_name: Package name (for dependency errors)

        Returns:
            Commit message string
        """
        # Get filename only for cleaner message
        filename = os.path.basename(file_path)

        if error_type == "dependency" and package_name:
            title = f"fix(auto): add missing dependency {package_name}"
        else:
            title = f"fix(auto): resolve {error_type} error in {filename}"

        message = f"""{title}

- Error type: {error_type}
- File: {file_path}
- Fixed by: GitLab CI Auto-Fix Agent
- Pipeline ID: {pipeline_id}
- Job ID: {job_id}

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"""

        return message

    def push_branch(self, branch_name: str) -> None:
        """
        Push branch to remote.

        Args:
            branch_name: Name of branch to push
        """
        try:
            logger.info(f"[GIT] Pushing branch {branch_name} to remote")

            # Push with upstream tracking
            self.repo.git.push("--set-upstream", "origin", branch_name)

            logger.info("[GIT] Push successful")

        except GitCommandError as e:
            logger.error(f"[GIT] Failed to push: {e}")

            if "Permission denied" in str(e) or "forbidden" in str(e).lower():
                print(
                    f"\n[MANUAL ACTION REQUIRED] Git push failed - permission denied.\n"
                    f"Your GitLab token needs 'write_repository' permission.\n"
                    f"Go to GitLab → Settings → Access Tokens → create new token with:\n"
                    f"  - Scopes: 'api' and 'write_repository'\n"
                    f"  - Update GITLAB_TOKEN in your .env file\n"
                )

            raise

    def open_merge_request(
        self,
        branch_name: str,
        pipeline_id: str,
        job_info: dict,
        error_info: dict,
        fix_result: dict,
        validation_result: dict
    ) -> str:
        """
        Create a merge request on GitLab.

        Args:
            branch_name: Source branch name
            pipeline_id: Pipeline ID
            job_info: Job information
            error_info: Error details
            fix_result: Fix operation result
            validation_result: Validation result

        Returns:
            Merge request URL
        """
        try:
            # Create MR title
            title = f"fix: auto-resolved {error_info['error_type']} in pipeline #{pipeline_id}"

            # Create MR description
            description = self._create_mr_description(
                pipeline_id, job_info, error_info, fix_result, validation_result
            )

            # MR API endpoint
            mr_url = f"{self.base_url}/projects/{self.config.gitlab_project_id}/merge_requests"

            # MR data
            mr_data = {
                "source_branch": branch_name,
                "target_branch": self.config.gitlab_default_branch,
                "title": title,
                "description": description,
                "remove_source_branch": True,
                "labels": ["auto-fix", error_info["error_type"]]
            }

            # Create MR
            with httpx.Client(timeout=30.0) as client:
                response = client.post(mr_url, headers=self.headers, json=mr_data)
                response.raise_for_status()
                mr_response = response.json()

            mr_web_url = mr_response["web_url"]
            logger.info(f"[GIT] Merge Request created: {mr_web_url}")
            print(f"\n[MR CREATED] {mr_web_url}\n")

            return mr_web_url

        except Exception as e:
            logger.error(f"[GIT] Failed to create merge request: {e}")
            raise

    def _create_mr_description(
        self,
        pipeline_id: str,
        job_info: dict,
        error_info: dict,
        fix_result: dict,
        validation_result: dict
    ) -> str:
        """
        Create detailed MR description.

        Returns:
            Markdown formatted description
        """
        validation_status = "✅ Passed" if validation_result["valid"] else "❌ Failed"
        validator_used = validation_result.get("validator_used", "none")

        description = f"""## Auto-Fix Report

**Pipeline:** #{pipeline_id}
**Job:** {job_info.get('job_name', 'N/A')} (#{job_info.get('job_id', 'N/A')})
**Error Type:** {error_info['error_type']}
**Confidence:** {error_info.get('confidence', 0):.0%}

## Root Cause

```
{error_info['error_message']}
```

**File:** `{error_info.get('error_file', 'N/A')}`
**Line:** {error_info.get('error_line', 'N/A')}

## Fix Applied

{fix_result.get('fix_applied', 'N/A')}

**File modified:** `{fix_result.get('file_modified', 'N/A')}`
**Strategy:** {fix_result.get('strategy', 'N/A')}

## Validation

- Syntax check: {validation_status}
- Validator used: {validator_used}

---

*This MR was created automatically by the GitLab CI Auto-Fix Agent*
"""

        return description


if __name__ == "__main__":
    # Test git manager
    import sys
    sys.path.insert(0, "..")

    from config import load_config

    try:
        config = load_config()
        git_manager = GitManager(config)

        print("Git manager initialized successfully")
        print(f"Repository path: {git_manager.repo_path}")
        print(f"Current branch: {git_manager.repo.active_branch.name}")

    except SystemExit:
        print("Configuration error - cannot test git manager")
