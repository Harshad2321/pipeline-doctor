"""
Report generator for fix operations.
Creates structured reports in terminal and JSON format.
"""

import json
import os
from datetime import datetime
from pathlib import Path

from loguru import logger


class Reporter:
    """Generates and saves fix reports."""

    def __init__(self, reports_dir: str = "reports"):
        """
        Initialize reporter.

        Args:
            reports_dir: Directory to save JSON reports
        """
        self.reports_dir = reports_dir
        os.makedirs(reports_dir, exist_ok=True)

    def generate_report(
        self,
        pipeline_id: str,
        job_info: dict,
        error_info: dict,
        fix_result: dict,
        pipeline_result: dict,
        mr_url: str = None,
        start_time: float = None
    ) -> dict:
        """
        Generate comprehensive fix report.

        Args:
            pipeline_id: Pipeline ID
            job_info: Job metadata
            error_info: Error classification details
            fix_result: Fix operation result
            pipeline_result: Pipeline re-run result
            mr_url: Merge request URL (optional)
            start_time: Start timestamp for duration calc

        Returns:
            Report dictionary
        """
        # Calculate duration
        if start_time:
            duration = datetime.now().timestamp() - start_time
        else:
            duration = 0

        # Build report
        report = {
            "timestamp": datetime.now().isoformat(),
            "pipeline_id": pipeline_id,
            "job": {
                "id": job_info.get("job_id"),
                "name": job_info.get("job_name"),
                "stage": job_info.get("stage"),
                "url": job_info.get("web_url")
            },
            "error": {
                "type": error_info["error_type"],
                "message": error_info["error_message"],
                "file": error_info.get("error_file"),
                "line": error_info.get("error_line"),
                "confidence": error_info.get("confidence"),
                "language": error_info.get("language")
            },
            "fix": {
                "applied": fix_result.get("fix_applied"),
                "file_modified": fix_result.get("file_modified"),
                "strategy": fix_result.get("strategy"),
                "success": fix_result.get("success", False)
            },
            "pipeline_rerun": {
                "id": pipeline_result.get("pipeline_id"),
                "status": pipeline_result.get("status"),
                "url": pipeline_result.get("web_url"),
                "duration_seconds": pipeline_result.get("duration_seconds")
            },
            "merge_request": {
                "url": mr_url
            } if mr_url else None,
            "total_duration_seconds": int(duration)
        }

        # Print to terminal
        self._print_terminal_report(report)

        # Save JSON report
        report_path = self._save_json_report(report, pipeline_id)

        logger.info(f"[REPORTER] Report saved to {report_path}")

        return report

    def _print_terminal_report(self, report: dict) -> None:
        """Print structured report to terminal."""
        pipeline_id = report["pipeline_id"]
        error_type = report["error"]["type"]
        error_message = report["error"]["message"]
        file_modified = report["fix"].get("file_modified", "N/A")
        strategy = report["fix"].get("strategy", "N/A")
        pipeline_status = report["pipeline_rerun"]["status"]
        mr_url = report.get("merge_request")
        duration = report["total_duration_seconds"]

        # Determine success icon
        if pipeline_status == "success":
            status_icon = "✅"
            status_text = "SUCCESS"
        elif pipeline_status in ["failed", "canceled"]:
            status_icon = "❌"
            status_text = "FAILED"
        else:
            status_icon = "⏳"
            status_text = pipeline_status.upper()

        print("\n" + "=" * 70)
        print(f"  AUTO-FIX REPORT - Pipeline #{pipeline_id}")
        print("=" * 70)
        print(f"\n{status_icon} Status: {status_text}")
        print(f"\n📊 Error Details:")
        print(f"  Type:     {error_type}")
        print(f"  Message:  {error_message[:100]}{'...' if len(error_message) > 100 else ''}")
        print(f"\n🔧 Fix Applied:")
        print(f"  File:     {file_modified}")
        print(f"  Strategy: {strategy}")
        print(f"\n⏱️  Duration: {duration}s")

        if mr_url:
            print(f"\n🔀 Merge Request: {mr_url['url']}")

        print("\n" + "=" * 70 + "\n")

    def _save_json_report(self, report: dict, pipeline_id: str) -> str:
        """
        Save report as JSON file.

        Args:
            report: Report dictionary
            pipeline_id: Pipeline ID for filename

        Returns:
            Path to saved report
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"fix-{pipeline_id}-{timestamp}.json"
        filepath = os.path.join(self.reports_dir, filename)

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

            return filepath

        except Exception as e:
            logger.error(f"[REPORTER] Failed to save JSON report: {e}")
            return None

    def print_stats(self, stats: dict) -> None:
        """
        Print fix history statistics.

        Args:
            stats: Statistics dictionary from memory
        """
        total = stats.get("total_fixes", 0)
        success = stats.get("successful_fixes", 0)
        rate = stats.get("success_rate", 0)
        escalated = stats.get("escalated", 0)
        common_errors = stats.get("common_errors", [])

        print("\n" + "=" * 50)
        print("  FIX HISTORY STATISTICS")
        print("=" * 50)
        print(f"\n📈 Overall Performance:")
        print(f"  Total fixes:      {total}")
        print(f"  Successful:       {success}")
        print(f"  Success rate:     {rate}%")
        print(f"  Escalated:        {escalated}")

        if common_errors:
            print(f"\n🔝 Most Common Error Types:")
            for error in common_errors[:5]:
                error_type = error.get("error_type", "unknown")
                count = error.get("count", 0)
                print(f"  {error_type:15s} {count:3d} occurrences")

        print("\n" + "=" * 50 + "\n")
