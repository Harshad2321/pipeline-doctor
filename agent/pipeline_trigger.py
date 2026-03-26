"""
Pipeline trigger and status monitor.
Re-triggers pipelines after fixes and monitors their completion.
"""

import time
from typing import Optional

import httpx
from loguru import logger

from config import Config


class PipelineTrigger:
    """Triggers and monitors GitLab pipelines."""

    def __init__(self, config: Config):
        """
        Initialize pipeline trigger.

        Args:
            config: Configuration object
        """
        self.config = config
        self.base_url = f"{config.gitlab_url}/api/v4"
        self.headers = {
            "PRIVATE-TOKEN": config.gitlab_token,
            "Content-Type": "application/json"
        }

    def retrigger_pipeline(self, branch_name: str) -> dict:
        """
        Trigger a new pipeline on a branch and monitor its status.

        Args:
            branch_name: Branch to trigger pipeline on

        Returns:
            Dict with pipeline_id, status, web_url, duration_seconds
        """
        # Step 1: Trigger the pipeline
        pipeline_id = self._trigger_pipeline_on_branch(branch_name)

        if not pipeline_id:
            return {
                "pipeline_id": None,
                "status": "failed_to_trigger",
                "web_url": None,
                "duration_seconds": 0
            }

        # Step 2: Monitor pipeline status
        return self._monitor_pipeline(pipeline_id)

    def _trigger_pipeline_on_branch(self, branch_name: str) -> Optional[str]:
        """
        Trigger a pipeline on a specific branch.

        Args:
            branch_name: Branch name

        Returns:
            Pipeline ID or None if failed
        """
        url = f"{self.base_url}/projects/{self.config.gitlab_project_id}/pipeline"
        data = {"ref": branch_name}

        try:
            logger.info(f"[PIPELINE] Triggering pipeline on branch: {branch_name}")

            with httpx.Client(timeout=30.0) as client:
                response = client.post(url, headers=self.headers, json=data)
                response.raise_for_status()
                pipeline_data = response.json()

            pipeline_id = pipeline_data["id"]
            web_url = pipeline_data["web_url"]

            logger.info(f"[PIPELINE] Pipeline #{pipeline_id} triggered: {web_url}")
            print(f"\n[PIPELINE TRIGGERED] #{pipeline_id}\n  URL: {web_url}\n")

            return str(pipeline_id)

        except httpx.HTTPError as e:
            logger.error(f"[PIPELINE] Failed to trigger pipeline: {e}")
            return None

    def _monitor_pipeline(self, pipeline_id: str) -> dict:
        """
        Monitor pipeline status until completion.

        Polls every 20 seconds, max 20 attempts (~7 minutes).

        Args:
            pipeline_id: Pipeline ID to monitor

        Returns:
            Pipeline result dict
        """
        url = f"{self.base_url}/projects/{self.config.gitlab_project_id}/pipelines/{pipeline_id}"

        max_polls = 20
        poll_interval = 20  # seconds
        start_time = time.time()

        logger.info(f"[PIPELINE] Monitoring pipeline #{pipeline_id}")

        for attempt in range(1, max_polls + 1):
            try:
                with httpx.Client(timeout=30.0) as client:
                    response = client.get(url, headers=self.headers)
                    response.raise_for_status()
                    pipeline_data = response.json()

                status = pipeline_data["status"]
                web_url = pipeline_data["web_url"]

                logger.info(f"[PIPELINE] Status: {status} (attempt {attempt}/{max_polls})")

                # Check if pipeline is complete
                if status in ["success", "failed", "canceled", "skipped"]:
                    duration = time.time() - start_time

                    if status == "success":
                        logger.info(f"[SUCCESS] ✅ Pipeline passed after auto-fix!")
                        print(
                            f"\n[SUCCESS] ✅ Pipeline #{pipeline_id} passed!\n"
                            f"  Duration: {duration:.1f}s\n"
                            f"  URL: {web_url}\n"
                        )
                    else:
                        logger.warning(f"[PIPELINE] Pipeline {status}: {web_url}")
                        print(
                            f"\n[PIPELINE {status.upper()}] Pipeline #{pipeline_id} {status}\n"
                            f"  Duration: {duration:.1f}s\n"
                            f"  URL: {web_url}\n"
                        )

                    return {
                        "pipeline_id": pipeline_id,
                        "status": status,
                        "web_url": web_url,
                        "duration_seconds": int(duration)
                    }

                # Still running, wait and poll again
                if attempt < max_polls:
                    time.sleep(poll_interval)

            except httpx.HTTPError as e:
                logger.error(f"[PIPELINE] Error polling pipeline status: {e}")
                break

        # Timeout reached
        duration = time.time() - start_time
        logger.warning(f"[PIPELINE] Monitoring timeout after {duration:.1f}s")
        print(
            f"\n[PIPELINE TIMEOUT] Pipeline #{pipeline_id} still running after {duration:.1f}s\n"
            f"  The agent will stop monitoring, but the pipeline continues.\n"
            f"  Check status manually at: {web_url}\n"
        )

        return {
            "pipeline_id": pipeline_id,
            "status": "timeout",
            "web_url": pipeline_data.get("web_url", ""),
            "duration_seconds": int(duration)
        }

    def get_pipeline_status(self, pipeline_id: str) -> str:
        """
        Get current status of a pipeline.

        Args:
            pipeline_id: Pipeline ID

        Returns:
            Status string
        """
        url = f"{self.base_url}/projects/{self.config.gitlab_project_id}/pipelines/{pipeline_id}"

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(url, headers=self.headers)
                response.raise_for_status()
                pipeline_data = response.json()

            return pipeline_data["status"]

        except Exception as e:
            logger.error(f"[PIPELINE] Failed to get pipeline status: {e}")
            return "unknown"
