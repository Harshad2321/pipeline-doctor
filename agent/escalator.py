"""
Escalation handler for when auto-fix attempts fail.
Creates GitLab issues with full context for human review.
"""

import httpx
from loguru import logger

from config import Config
from agent.memory import FixMemory


class Escalator:
    """Handles escalation when auto-fix fails after max attempts."""

    def __init__(self, config: Config, memory: FixMemory):
        """
        Initialize escalator.

        Args:
            config: Configuration object
            memory: Fix memory database
        """
        self.config = config
        self.memory = memory
        self.base_url = f"{config.gitlab_url}/api/v4"
        self.headers = {
            "PRIVATE-TOKEN": config.gitlab_token,
            "Content-Type": "application/json"
        }

    def escalate(
        self,
        pipeline_id: str,
        job_id: str,
        job_info: dict,
        error_info: dict,
        all_attempts: list[dict]
    ) -> None:
        """
        Escalate to human review after max fix attempts.

        Actions:
        1. Print clear escalation message
        2. Save escalation to memory
        3. Create GitLab issue with full context

        Args:
            pipeline_id: Pipeline ID
            job_id: Job ID
            job_info: Job metadata
            error_info: Error details
            all_attempts: List of all fix attempts made
        """
        max_attempts = self.config.max_fix_attempts
        error_type = error_info.get("error_type", "unknown")
        error_message = error_info.get("error_message", "No error message")
        web_url = job_info.get("web_url", "N/A")

        logger.warning(
            f"[ESCALATION] Max attempts ({max_attempts}) exceeded for "
            f"pipeline #{pipeline_id}, job #{job_id}"
        )

        # Print escalation notice
        self._print_escalation_notice(
            pipeline_id, job_id, error_type, max_attempts, web_url
        )

        # Save to memory with escalation flag
        self.memory.save_fix(
            pipeline_id=pipeline_id,
            job_id=job_id,
            error_type=error_type,
            error_message=error_message,
            fix_applied="Escalated to human review after max attempts",
            fix_strategy="escalated",
            error_file=error_info.get("error_file"),
            pipeline_passed=False,
            attempt_number=-1  # -1 indicates escalation
        )

        # Create GitLab issue
        issue_url = self._create_escalation_issue(
            pipeline_id, job_id, job_info, error_info, all_attempts, max_attempts
        )

        if issue_url:
            print(f"\n[ISSUE CREATED] {issue_url}\n")

    def _print_escalation_notice(
        self,
        pipeline_id: str,
        job_id: str,
        error_type: str,
        max_attempts: int,
        web_url: str
    ) -> None:
        """Print a clear escalation notice to terminal."""
        box_width = 60
        print("\n" + "=" * box_width)
        print("║" + " " * (box_width - 2) + "║")
        print("║" + " [ESCALATION] HUMAN REVIEW NEEDED ".center(box_width - 2) + "║")
        print("║" + " " * (box_width - 2) + "║")
        print("=" * box_width)
        print(f"  Pipeline:    #{pipeline_id}")
        print(f"  Job:         #{job_id}")
        print(f"  Error Type:  {error_type}")
        print(f"  Attempts:    {max_attempts}/{max_attempts}")
        print(f"  Job URL:     {web_url}")
        print("=" * box_width + "\n")

    def _create_escalation_issue(
        self,
        pipeline_id: str,
        job_id: str,
        job_info: dict,
        error_info: dict,
        all_attempts: list[dict],
        max_attempts: int
    ) -> str:
        """
        Create a GitLab issue for escalation.

        Args:
            pipeline_id: Pipeline ID
            job_id: Job ID
            job_info: Job metadata
            error_info: Error information
            all_attempts: All fix attempts
            max_attempts: Maximum attempts configured

        Returns:
            Issue URL or None if creation failed
        """
        try:
            # Create issue title
            error_type = error_info.get("error_type", "unknown")
            title = f"[Auto-Fix Escalation] Pipeline #{pipeline_id} - {error_type} error"

            # Create issue description
            description = self._create_issue_description(
                pipeline_id, job_id, job_info, error_info, all_attempts, max_attempts
            )

            # Issue API endpoint
            issues_url = f"{self.base_url}/projects/{self.config.gitlab_project_id}/issues"

            # Issue data
            issue_data = {
                "title": title,
                "description": description,
                "labels": ["auto-fix-failed", f"error-{error_type}", "needs-review"]
            }

            # Create issue
            logger.info("[ESCALATION] Creating GitLab issue")

            with httpx.Client(timeout=30.0) as client:
                response = client.post(issues_url, headers=self.headers, json=issue_data)
                response.raise_for_status()
                issue_response = response.json()

            issue_web_url = issue_response["web_url"]
            logger.info(f"[ESCALATION] Issue created: {issue_web_url}")

            return issue_web_url

        except Exception as e:
            logger.error(f"[ESCALATION] Failed to create GitLab issue: {e}")
            print(
                f"\n[WARNING] Could not create GitLab issue automatically.\n"
                f"Please manually review the failed pipeline.\n"
                f"Error: {e}\n"
            )
            return None

    def _create_issue_description(
        self,
        pipeline_id: str,
        job_id: str,
        job_info: dict,
        error_info: dict,
        all_attempts: list[dict],
        max_attempts: int
    ) -> str:
        """
        Create detailed issue description with all context.

        Returns:
            Markdown formatted description
        """
        error_type = error_info.get("error_type", "unknown")
        error_message = error_info.get("error_message", "No error message")
        error_file = error_info.get("error_file", "N/A")
        error_line = error_info.get("error_line", "N/A")
        confidence = error_info.get("confidence", 0)
        language = error_info.get("language", "unknown")
        stage = error_info.get("stage", "unknown")
        job_name = job_info.get("job_name", "N/A")
        job_url = job_info.get("web_url", "N/A")

        # Build attempts history
        attempts_md = ""
        for i, attempt in enumerate(all_attempts, 1):
            strategy = attempt.get("strategy", "unknown")
            success = attempt.get("success", False)
            status_icon = "✅" if success else "❌"

            attempts_md += f"\n**Attempt {i}:** {status_icon} Strategy: `{strategy}`"

            if not success:
                reason = attempt.get("fix_applied", "Unknown reason")
                attempts_md += f"\n  - Failed: {reason}"

        description = f"""## Auto-Fix Escalation

The GitLab CI Auto-Fix Agent attempted to fix this error {max_attempts} times but was unsuccessful.
Manual review and intervention are required.

---

## Pipeline Information

- **Pipeline:** #{pipeline_id}
- **Job:** {job_name} (#{job_id})
- **Job URL:** {job_url}
- **Stage:** {stage}

---

## Error Details

- **Error Type:** `{error_type}`
- **Classification Confidence:** {confidence:.0%}
- **Language:** {language}
- **File:** `{error_file}`
- **Line:** {error_line}

### Error Message

```
{error_message}
```

---

## Fix Attempts

{attempts_md}

---

## Next Steps

1. Review the pipeline logs: {job_url}
2. Investigate the root cause of the error
3. Apply a manual fix to the codebase
4. Close this issue once resolved

---

*This issue was created automatically by the GitLab CI Auto-Fix Agent*
"""

        return description

    def escalate_unknown_error(
        self,
        pipeline_id: str,
        job_id: str,
        job_info: dict,
        error_info: dict
    ) -> None:
        """
        Special escalation for unknown error types (immediate, no retries).

        Args:
            pipeline_id: Pipeline ID
            job_id: Job ID
            job_info: Job metadata
            error_info: Error details
        """
        logger.warning(f"[ESCALATION] Unknown error type in pipeline #{pipeline_id}")

        error_message = error_info.get("error_message", "No error message")
        web_url = job_info.get("web_url", "N/A")

        print(
            f"\n[ESCALATION] Unknown error type - cannot auto-fix\n"
            f"  Pipeline: #{pipeline_id}\n"
            f"  Job: #{job_id}\n"
            f"  Error: {error_message}\n"
            f"  URL: {web_url}\n"
        )

        # Save to memory
        self.memory.save_fix(
            pipeline_id=pipeline_id,
            job_id=job_id,
            error_type="unknown",
            error_message=error_message,
            fix_applied="Unknown error type - escalated immediately",
            fix_strategy="escalated_unknown",
            error_file=error_info.get("error_file"),
            pipeline_passed=False,
            attempt_number=-1
        )
