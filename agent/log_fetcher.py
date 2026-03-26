"""
Fetches and cleans job logs from GitLab pipelines.
Handles log size limits and removes ANSI codes for clean parsing.
"""

import re
from typing import Optional

import httpx
from loguru import logger

from config import Config


class LogFetcher:
    """Fetches and processes job logs from GitLab."""

    # ANSI color code regex pattern
    ANSI_ESCAPE_PATTERN = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    # Common timestamp patterns to remove
    TIMESTAMP_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[^\s]*\s*')

    def __init__(self, config: Config):
        """
        Initialize the log fetcher.

        Args:
            config: Configuration object with GitLab credentials
        """
        self.config = config
        self.base_url = f"{config.gitlab_url}/api/v4"
        self.headers = {
            "PRIVATE-TOKEN": config.gitlab_token,
            "Content-Type": "application/json"
        }

    def get_failed_job_logs(self, pipeline_id: str) -> list[dict]:
        """
        Fetch logs from all failed jobs in a pipeline.

        Args:
            pipeline_id: GitLab pipeline ID

        Returns:
            List of job log dictionaries with:
                - job_id: Job ID
                - job_name: Job name
                - stage: Pipeline stage
                - raw_logs: Original logs
                - cleaned_logs: Processed logs
                - failure_reason: GitLab's failure reason (if available)
        """
        # Step 1: Get all jobs for the pipeline
        jobs_url = f"{self.base_url}/projects/{self.config.gitlab_project_id}/pipelines/{pipeline_id}/jobs"

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(jobs_url, headers=self.headers)
                response.raise_for_status()
                jobs = response.json()

        except httpx.HTTPError as e:
            logger.error(f"[LOG FETCHER] Failed to fetch jobs for pipeline {pipeline_id}: {e}")
            return []

        # Step 2: Filter for failed jobs
        failed_jobs = [job for job in jobs if job["status"] == "failed"]

        if not failed_jobs:
            logger.warning(f"[LOG FETCHER] No failed jobs found in pipeline {pipeline_id}")
            return []

        logger.info(f"[LOG FETCHER] Found {len(failed_jobs)} failed job(s) in pipeline {pipeline_id}")

        # Step 3: Fetch logs for each failed job
        job_logs = []
        for job in failed_jobs:
            job_id = job["id"]
            job_name = job["name"]
            stage = job["stage"]
            failure_reason = job.get("failure_reason", "unknown")

            logs = self._fetch_job_trace(job_id)

            if logs:
                cleaned_logs = self._clean_logs(logs)
                job_logs.append({
                    "job_id": str(job_id),
                    "job_name": job_name,
                    "stage": stage,
                    "raw_logs": logs,
                    "cleaned_logs": cleaned_logs,
                    "failure_reason": failure_reason,
                    "web_url": job.get("web_url", "")
                })

                log_length = len(cleaned_logs)
                logger.info(f"[LOG FETCHER] Fetched {log_length} chars of logs from job {job_id} ({job_name})")

        return job_logs

    def _fetch_job_trace(self, job_id: str) -> Optional[str]:
        """
        Fetch raw trace/log for a specific job.

        Args:
            job_id: GitLab job ID

        Returns:
            Raw log string or None if fetch fails
        """
        trace_url = f"{self.base_url}/projects/{self.config.gitlab_project_id}/jobs/{job_id}/trace"

        try:
            with httpx.Client(timeout=60.0) as client:  # Longer timeout for large logs
                response = client.get(trace_url, headers=self.headers)
                response.raise_for_status()
                return response.text

        except httpx.HTTPError as e:
            logger.error(f"[LOG FETCHER] Failed to fetch trace for job {job_id}: {e}")
            return None

    def _clean_logs(self, raw_logs: str) -> str:
        """
        Clean logs by removing ANSI codes, timestamps, and empty lines.
        Truncates if logs are too large (keeps first 3000 + last 3000 chars).

        Args:
            raw_logs: Raw log content

        Returns:
            Cleaned log string
        """
        # Remove ANSI color codes
        cleaned = self.ANSI_ESCAPE_PATTERN.sub('', raw_logs)

        # Remove timestamps from start of lines
        lines = cleaned.split('\n')
        cleaned_lines = []

        for line in lines:
            # Remove timestamp if present
            line = self.TIMESTAMP_PATTERN.sub('', line)
            # Remove excessive whitespace
            line = line.strip()
            # Keep non-empty lines
            if line:
                cleaned_lines.append(line)

        cleaned = '\n'.join(cleaned_lines)

        # Truncate if too large (keep most relevant parts)
        MAX_CHARS = 8000
        if len(cleaned) > MAX_CHARS:
            first_part = cleaned[:3000]
            last_part = cleaned[-3000:]
            cleaned = (
                f"{first_part}\n\n"
                f"[... {len(cleaned) - 6000} characters truncated ...]\n\n"
                f"{last_part}"
            )
            logger.debug(f"[LOG FETCHER] Truncated logs from {len(raw_logs)} to {len(cleaned)} chars")

        return cleaned

    def extract_error_context(self, cleaned_logs: str, context_lines: int = 20) -> str:
        """
        Extract the most relevant error context from logs.
        Finds error indicators and returns surrounding lines.

        Args:
            cleaned_logs: Cleaned log content
            context_lines: Number of lines to include after error indicator

        Returns:
            Extracted error context
        """
        error_indicators = [
            "error:",
            "Error:",
            "ERROR:",
            "failed",
            "Failed",
            "FAILED",
            "exception",
            "Exception",
            "Traceback",
            "SyntaxError",
            "ModuleNotFoundError",
            "ImportError"
        ]

        lines = cleaned_logs.split('\n')

        # Find first line with error indicator
        error_line_idx = None
        for i, line in enumerate(lines):
            if any(indicator in line for indicator in error_indicators):
                error_line_idx = i
                break

        if error_line_idx is None:
            # No clear error found, return last N lines
            return '\n'.join(lines[-context_lines:])

        # Return error line + context
        start_idx = max(0, error_line_idx - 5)  # 5 lines before error
        end_idx = min(len(lines), error_line_idx + context_lines)  # N lines after error

        return '\n'.join(lines[start_idx:end_idx])
