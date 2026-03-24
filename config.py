"""
Configuration module for GitLab CI Auto-Fix Agent.
Loads and validates all environment variables required for the agent to function.
"""

import os
import sys
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    """Frozen configuration dataclass with validated environment variables."""

    gitlab_url: str
    gitlab_token: str
    gitlab_project_id: str
    gitlab_default_branch: str
    openai_api_key: str
    openai_model: str
    max_fix_attempts: int
    poll_interval_seconds: int
    dry_run: bool
    repo_path: Optional[str] = None


def _print_manual_action(message: str) -> None:
    """Print manual action required message to stderr."""
    print(f"\n[MANUAL ACTION REQUIRED] {message}\n", file=sys.stderr)


def _validate_url(url: str, var_name: str) -> None:
    """Validate that a string is a properly formatted URL."""
    try:
        result = urlparse(url)
        if not all([result.scheme, result.netloc]):
            raise ValueError(f"Invalid URL format")
    except Exception as e:
        _print_manual_action(
            f"{var_name} must be a valid URL (e.g., https://gitlab.com). "
            f"Current value: {url}. Error: {e}"
        )
        sys.exit(1)


def _validate_integer_range(value: str, var_name: str, min_val: int, max_val: int) -> int:
    """Validate that a string can be converted to an integer within a range."""
    try:
        int_value = int(value)
        if not (min_val <= int_value <= max_val):
            raise ValueError(f"Must be between {min_val} and {max_val}")
        return int_value
    except ValueError as e:
        _print_manual_action(
            f"{var_name} must be an integer between {min_val} and {max_val}. "
            f"Current value: {value}. Error: {e}"
        )
        sys.exit(1)


def _get_required_env_var(var_name: str) -> str:
    """Get a required environment variable or exit with clear error message."""
    value = os.getenv(var_name)
    if not value or value.strip() == "" or value.startswith("your_"):
        _print_manual_action(
            f"Missing or invalid environment variable: {var_name}\n"
            f"Please add it to your .env file.\n\n"
            f"Required .env variables:\n"
            f"  - GITLAB_TOKEN: Go to GitLab → Settings → Access Tokens → "
            f"create with 'api' and 'write_repository' scopes\n"
            f"  - GITLAB_PROJECT_ID: Found on your GitLab project main page under the project name\n"
            f"  - OPENAI_API_KEY: Get from https://platform.openai.com/api-keys\n"
            f"  - OPENAI_MODEL: Use 'gpt-4o' (recommended) or 'gpt-4-turbo'\n\n"
            f"Copy .env.example to .env and fill in your actual credentials."
        )
        sys.exit(1)
    return value.strip()


def load_config() -> Config:
    """
    Load configuration from environment variables.

    Validates all required variables and returns a frozen Config object.
    Exits with clear error messages if any required variable is missing or invalid.

    Returns:
        Config: Validated configuration object
    """
    # Load .env file if it exists
    env_file_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_file_path):
        _print_manual_action(
            f".env file not found at {env_file_path}\n"
            f"Please copy .env.example to .env and fill in your credentials:\n"
            f"  cp .env.example .env\n"
            f"Then edit .env with your actual values."
        )
        sys.exit(1)

    load_dotenv(env_file_path)

    # Load and validate required variables
    gitlab_url = _get_required_env_var("GITLAB_URL")
    _validate_url(gitlab_url, "GITLAB_URL")

    gitlab_token = _get_required_env_var("GITLAB_TOKEN")
    gitlab_project_id = _get_required_env_var("GITLAB_PROJECT_ID")
    gitlab_default_branch = _get_required_env_var("GITLAB_DEFAULT_BRANCH")
    openai_api_key = _get_required_env_var("OPENAI_API_KEY")
    openai_model = _get_required_env_var("OPENAI_MODEL")

    # Validate optional variables with defaults
    max_fix_attempts_str = os.getenv("MAX_FIX_ATTEMPTS", "3")
    max_fix_attempts = _validate_integer_range(
        max_fix_attempts_str, "MAX_FIX_ATTEMPTS", 1, 10
    )

    poll_interval_str = os.getenv("POLL_INTERVAL_SECONDS", "30")
    poll_interval = _validate_integer_range(
        poll_interval_str, "POLL_INTERVAL_SECONDS", 10, 300
    )

    # Parse boolean DRY_RUN flag
    dry_run_str = os.getenv("DRY_RUN", "false").lower()
    dry_run = dry_run_str in ("true", "1", "yes")

    # Optional repo path
    repo_path = os.getenv("REPO_PATH")
    if repo_path:
        repo_path = repo_path.strip()

    return Config(
        gitlab_url=gitlab_url,
        gitlab_token=gitlab_token,
        gitlab_project_id=gitlab_project_id,
        gitlab_default_branch=gitlab_default_branch,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        max_fix_attempts=max_fix_attempts,
        poll_interval_seconds=poll_interval,
        dry_run=dry_run,
        repo_path=repo_path
    )


if __name__ == "__main__":
    # Test configuration loading
    try:
        config = load_config()
        print("✅ Configuration loaded successfully!")
        print(f"GitLab URL: {config.gitlab_url}")
        print(f"Project ID: {config.gitlab_project_id}")
        print(f"OpenAI Model: {config.openai_model}")
        print(f"Max attempts: {config.max_fix_attempts}")
        print(f"Poll interval: {config.poll_interval_seconds}s")
        print(f"Dry run: {config.dry_run}")
    except SystemExit:
        pass
