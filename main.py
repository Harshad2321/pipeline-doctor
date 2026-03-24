"""
GitLab CI Auto-Fix Agent - Main entry point.
Production-grade autonomous CI/CD error fixing agent.
"""

import sys
import time
from datetime import datetime

import schedule
import typer
from loguru import logger

from config import load_config
from agent.watcher import PipelineWatcher
from agent.log_fetcher import LogFetcher
from agent.classifier import ErrorClassifier
from agent.fix_engine import FixEngine
from agent.git_manager import GitManager
from agent.pipeline_trigger import PipelineTrigger
from agent.escalator import Escalator
from agent.memory import FixMemory
from agent.reporter import Reporter


# Initialize Typer CLI app
app = typer.Typer(help="GitLab CI Auto-Fix Agent - Autonomous CI/CD error fixer")

# Configure logging
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level="INFO"
)
logger.add(
    "logs/agent_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="30 days",
    level="DEBUG"
)


def run_agent_cycle(
    config,
    watcher,
    log_fetcher,
    classifier,
    fix_engine,
    git_manager,
    pipeline_trigger,
    escalator,
    reporter,
    dry_run
):
    """
    Run one complete agent cycle.

    This is the main orchestration function that:
    1. Checks for failed pipelines
    2. Fetches and classifies errors
    3. Attempts fixes
    4. Validates and commits
    5. Opens MR and re-triggers pipeline
    6. Handles escalation if needed
    """
    # Step 1: Check for failed pipelines
    failed_pipelines = watcher.get_failed_pipelines()

    if not failed_pipelines:
        return

    # Process each failed pipeline
    for pipeline_info in failed_pipelines:
        pipeline_id = str(pipeline_info["id"])
        pipeline_ref = pipeline_info["ref"]

        logger.info(f"[AGENT] Processing pipeline #{pipeline_id} on {pipeline_ref}")

        # Mark as processed to avoid re-processing
        watcher.mark_as_processed(pipeline_id)

        # Check if we've already attempted to fix this pipeline
        existing_attempts = fix_engine.memory.get_attempts_for_pipeline(pipeline_id)

        if len(existing_attempts) >= config.max_fix_attempts:
            logger.warning(
                f"[AGENT] Pipeline #{pipeline_id} already has {len(existing_attempts)} "
                f"fix attempts - skipping"
            )
            continue

        start_time = time.time()

        # Step 2: Fetch job logs
        job_logs = log_fetcher.get_failed_job_logs(pipeline_id)

        if not job_logs:
            logger.warning(f"[AGENT] No failed job logs found for pipeline #{pipeline_id}")
            continue

        # Process first failed job (can be extended to handle multiple jobs)
        job_info = job_logs[0]
        job_id = job_info["job_id"]
        cleaned_logs = job_info["cleaned_logs"]

        # Step 3: Classify error
        error_info = classifier.classify_error(cleaned_logs, job_info)

        # Step 4: Run fix engine
        attempt_number = len(existing_attempts) + 1

        fix_engine_result = fix_engine.run_fix(
            pipeline_id=pipeline_id,
            job_info=job_info,
            error_info=error_info,
            repo_path=git_manager.repo_path,
            cleaned_logs=cleaned_logs,
            attempt_number=attempt_number
        )

        if not fix_engine_result["success"]:
            # Check if we should escalate
            if attempt_number >= config.max_fix_attempts:
                escalator.escalate(
                    pipeline_id=pipeline_id,
                    job_id=job_id,
                    job_info=job_info,
                    error_info=error_info,
                    all_attempts=existing_attempts + [fix_engine_result["fix_result"]]
                )
            else:
                logger.info(
                    f"[AGENT] Fix attempt {attempt_number}/{config.max_fix_attempts} failed - "
                    f"will retry on next cycle"
                )
            continue

        fix_result = fix_engine_result["fix_result"]
        file_modified = fix_result.get("file_modified")

        if not file_modified:
            logger.warning("[AGENT] No file was modified - skipping Git operations")
            continue

        # Step 5: Git operations (only if not dry run)
        if dry_run:
            logger.info("[DRY RUN] Skipping Git operations and pipeline trigger")
            print(
                f"\n[DRY RUN MODE]\n"
                f"  Would have:\n"
                f"  1. Created branch auto-fix/job-{job_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}\n"
                f"  2. Committed fix to {file_modified}\n"
                f"  3. Pushed to remote and opened MR\n"
                f"  4. Re-triggered pipeline\n"
            )

            # Generate report even in dry run
            reporter.generate_report(
                pipeline_id=pipeline_id,
                job_info=job_info,
                error_info=error_info,
                fix_result=fix_result,
                pipeline_result={"status": "dry_run", "duration_seconds": 0},
                start_time=start_time
            )
            continue

        try:
            # Create branch
            branch_name = git_manager.create_fix_branch(job_id)

            # Commit fix
            commit_sha = git_manager.commit_fix(
                file_modified=file_modified,
                error_type=error_info["error_type"],
                job_id=job_id,
                pipeline_id=pipeline_id,
                package_name=error_info.get("package_name")
            )

            # Push branch
            git_manager.push_branch(branch_name)

            # Open merge request
            mr_url = git_manager.open_merge_request(
                branch_name=branch_name,
                pipeline_id=pipeline_id,
                job_info=job_info,
                error_info=error_info,
                fix_result=fix_result,
                validation_result=fix_engine_result["validation_result"]
            )

            # Step 6: Re-trigger pipeline on fix branch
            pipeline_result = pipeline_trigger.retrigger_pipeline(branch_name)

            # Update memory with pipeline result
            if pipeline_result["status"] == "success":
                fix_engine.memory.update_result(pipeline_id, passed=True)

            # Step 7: Generate report
            reporter.generate_report(
                pipeline_id=pipeline_id,
                job_info=job_info,
                error_info=error_info,
                fix_result=fix_result,
                pipeline_result=pipeline_result,
                mr_url=mr_url,
                start_time=start_time
            )

            # Check if we should escalate after failed pipeline
            if pipeline_result["status"] == "failed" and attempt_number >= config.max_fix_attempts:
                all_attempts = existing_attempts + [fix_result]
                escalator.escalate(
                    pipeline_id=pipeline_id,
                    job_id=job_id,
                    job_info=job_info,
                    error_info=error_info,
                    all_attempts=all_attempts
                )

        except Exception as e:
            logger.error(f"[AGENT] Error during Git operations or pipeline trigger: {e}")
            print(f"\n[ERROR] Agent cycle failed: {e}\n")


@app.command()
def run(
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate without making changes")
):
    """
    Start the agent in continuous polling mode.
    Monitors GitLab for failed pipelines and fixes them automatically.
    """
    # Load configuration
    try:
        config = load_config()
    except SystemExit:
        return

    # Override dry run from config if specified
    if not dry_run:
        dry_run = config.dry_run

    # Initialize components
    logger.info("[AGENT] Initializing components...")

    memory = FixMemory()
    watcher = PipelineWatcher(config)
    log_fetcher = LogFetcher(config)
    classifier = ErrorClassifier()
    fix_engine = FixEngine(config, memory)
    git_manager = GitManager(config)
    pipeline_trigger = PipelineTrigger(config)
    escalator = Escalator(config, memory)
    reporter = Reporter()

    # Print startup banner
    mode = "DRY RUN" if dry_run else "LIVE"
    print("\n" + "=" * 60)
    print("  GitLab CI Auto-Fix Agent")
    print("=" * 60)
    print(f"  Project:      {config.gitlab_project_id}")
    print(f"  GitLab:       {config.gitlab_url}")
    print(f"  Mode:         {mode}")
    print(f"  Poll Interval: {config.poll_interval_seconds}s")
    print(f"  Max Attempts: {config.max_fix_attempts}")
    print("=" * 60)
    print("\n  Press Ctrl+C to stop\n")

    if dry_run:
        print("  [DRY RUN] No changes will be committed or pushed\n")

    # Schedule polling
    def job():
        try:
            run_agent_cycle(
                config,
                watcher,
                log_fetcher,
                classifier,
                fix_engine,
                git_manager,
                pipeline_trigger,
                escalator,
                reporter,
                dry_run
            )
        except Exception as e:
            logger.error(f"[AGENT] Cycle error: {e}")

    schedule.every(config.poll_interval_seconds).seconds.do(job)

    # Run immediately once
    logger.info("[AGENT] Running initial check...")
    job()

    # Main loop
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n[AGENT] Shutting down gracefully...\n")
        logger.info("[AGENT] Stopped by user")


@app.command()
def status():
    """
    Show fix history statistics from the database.
    """
    try:
        config = load_config()
        memory = FixMemory()
        reporter = Reporter()

        stats = memory.get_stats()
        reporter.print_stats(stats)

    except SystemExit:
        return


@app.command()
def fix_once(
    pipeline_id: str = typer.Argument(..., help="Pipeline ID to fix"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate without making changes")
):
    """
    Run the agent once on a specific pipeline (useful for testing).
    """
    try:
        config = load_config()
    except SystemExit:
        return

    # Override dry run
    if not dry_run:
        dry_run = config.dry_run

    logger.info(f"[AGENT] Running one-time fix for pipeline #{pipeline_id}")

    # Initialize components
    memory = FixMemory()
    watcher = PipelineWatcher(config)
    log_fetcher = LogFetcher(config)
    classifier = ErrorClassifier()
    fix_engine = FixEngine(config, memory)
    git_manager = GitManager(config)
    pipeline_trigger = PipelineTrigger(config)
    escalator = Escalator(config, memory)
    reporter = Reporter()

    # Manually add pipeline to watcher (simulate it being detected)
    print(f"\n[AGENT] Processing pipeline #{pipeline_id}...\n")

    # Run one cycle targeting this specific pipeline
    # (simplified version - just process this pipeline)
    job_logs = log_fetcher.get_failed_job_logs(pipeline_id)

    if not job_logs:
        print(f"\n[ERROR] No failed jobs found in pipeline #{pipeline_id}\n")
        return

    # Continue with normal flow...
    job_info = job_logs[0]
    cleaned_logs = job_info["cleaned_logs"]

    error_info = classifier.classify_error(cleaned_logs, job_info)

    print(f"\n[CLASSIFIED] Error type: {error_info['error_type']} "
          f"(confidence: {error_info.get('confidence', 0):.0%})\n")

    # ... rest of the fix process
    # (similar to run_agent_cycle but for single pipeline)


if __name__ == "__main__":
    app()
