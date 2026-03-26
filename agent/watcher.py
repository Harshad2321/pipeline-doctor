"""
GitLab pipeline watcher that polls for failed pipelines.
Tracks processed pipelines to avoid duplicate processing.
"""

import time
from typing import Optional

import httpx
from loguru import logger

from config import Config


class PipelineWatcher:
    """Watches GitLab for failed pipelines and tracks processed ones."""

    def __init__(self, config: Config):
        """
        Initialize the pipeline watcher.

        Args:
            config: Configuration object with GitLab credentials
        """
        self.config = config
        self.base_url = f"{config.gitlab_url}/api/v4"
        self.headers = {
            "PRIVATE-TOKEN": config.gitlab_token,
            "Content-Type": "application/json"
        }
        self.processed_pipeline_ids: set[str] = set()

    def get_failed_pipelines(self) -> list[dict]:
        """
        Fetch failed pipelines from GitLab API.

        Returns:
            List of failed pipeline dictionaries with id, status, ref, sha, created_at, web_url

        Handles:
            - 401: Bad token
            - 404: Bad project ID
            - 429: Rate limit (waits 60s)
        """
        url = f"{self.base_url}/projects/{self.config.gitlab_project_id}/pipelines"
        params = {
            "status": "failed",
            "per_page": 5,
            "order_by": "updated_at",
            "sort": "desc"
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(url, headers=self.headers, params=params)

                if response.status_code == 401:
                    logger.error("[WATCHER] Authentication failed - invalid GitLab token")
                    print(
                        "\n[MANUAL ACTION REQUIRED] GitLab authentication failed.\n"
                        "Your GITLAB_TOKEN is invalid or expired.\n"
                        "Go to GitLab → Settings → Access Tokens → create a new token with:\n"
                        "  - Scopes: 'api' and 'write_repository'\n"
                        "  - Update your .env file with the new token\n"
                    )
                    return []

                if response.status_code == 404:
                    logger.error(f"[WATCHER] Project not found - invalid project ID: {self.config.gitlab_project_id}")
                    print(
                        "\n[MANUAL ACTION REQUIRED] GitLab project not found.\n"
                        f"The project ID '{self.config.gitlab_project_id}' does not exist or you don't have access.\n"
                        "Check your GITLAB_PROJECT_ID in .env file.\n"
                        "Find it on your GitLab project's main page under the project name.\n"
                    )
                    return []

                if response.status_code == 429:
                    logger.warning("[WATCHER] Rate limit exceeded - waiting 60 seconds")
                    time.sleep(60)
                    return []

                response.raise_for_status()
                pipelines = response.json()

                # Filter out already processed pipelines
                new_pipelines = [
                    p for p in pipelines
                    if str(p["id"]) not in self.processed_pipeline_ids
                ]

                if new_pipelines:
                    logger.info(f"[WATCHER] Found {len(new_pipelines)} new failed pipeline(s)")
                    for pipeline in new_pipelines:
                        logger.debug(f"  - Pipeline #{pipeline['id']} on {pipeline['ref']}")
                else:
                    logger.debug("[WATCHER] No new failed pipelines found")

                return [
                    {
                        "id": p["id"],
                        "status": p["status"],
                        "ref": p["ref"],
                        "sha": p["sha"],
                        "created_at": p.get("created_at"),
                        "web_url": p["web_url"]
                    }
                    for p in new_pipelines
                ]

        except httpx.TimeoutException:
            logger.error("[WATCHER] Request timed out - GitLab may be slow or unreachable")
            return []

        except httpx.HTTPError as e:
            logger.error(f"[WATCHER] HTTP error occurred: {e}")
            return []

        except Exception as e:
            logger.error(f"[WATCHER] Unexpected error: {e}")
            return []

    def mark_as_processed(self, pipeline_id: str) -> None:
        """
        Mark a pipeline as processed to avoid reprocessing.

        Args:
            pipeline_id: GitLab pipeline ID
        """
        self.processed_pipeline_ids.add(str(pipeline_id))
        logger.debug(f"[WATCHER] Marked pipeline #{pipeline_id} as processed")

    def reset_processed(self) -> None:
        """
        Clear the list of processed pipelines.
        Useful for testing or when starting fresh.
        """
        count = len(self.processed_pipeline_ids)
        self.processed_pipeline_ids.clear()
        logger.info(f"[WATCHER] Reset processed pipeline tracking ({count} pipelines cleared)")

    def get_processed_count(self) -> int:
        """
        Get the number of processed pipelines.

        Returns:
            Number of pipelines marked as processed
        """
        return len(self.processed_pipeline_ids)
