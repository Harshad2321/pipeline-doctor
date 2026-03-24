"""
Fix engine that orchestrates the entire fix process.
Checks memory, calls appropriate fixer, validates, and saves results.
"""

from loguru import logger

from config import Config
from agent.memory import FixMemory
from agent.validator import FixValidator
from agent.fixers.dependency import DependencyFixer
from agent.fixers.syntax import SyntaxFixer
from agent.fixers.test_fixer import TestFixer
from agent.fixers.config_fixer import ConfigFixer


class FixEngine:
    """Orchestrates the fixing process for different error types."""

    def __init__(self, config: Config, memory: FixMemory):
        """
        Initialize fix engine with all fixers.

        Args:
            config: Configuration object
            memory: Fix memory database
        """
        self.config = config
        self.memory = memory
        self.validator = FixValidator()

        # Initialize fixers
        self.dependency_fixer = DependencyFixer()
        self.syntax_fixer = SyntaxFixer(config)
        self.test_fixer = TestFixer(config)
        self.config_fixer = ConfigFixer(config)

    def run_fix(
        self,
        pipeline_id: str,
        job_info: dict,
        error_info: dict,
        repo_path: str,
        cleaned_logs: str,
        attempt_number: int = 1
    ) -> dict:
        """
        Run the complete fix process for an error.

        Process:
        1. Check memory for past successful fix
        2. Call appropriate fixer based on error type
        3. Validate the fix
        4. Save to memory
        5. Return comprehensive result

        Args:
            pipeline_id: GitLab pipeline ID
            job_info: Job metadata
            error_info: Classified error information
            repo_path: Path to repository
            cleaned_logs: Cleaned job logs
            attempt_number: Current attempt number (1-based)

        Returns:
            Dict with success, fix_result, validation_result, used_memory
        """
        error_type = error_info["error_type"]
        error_message = error_info["error_message"]
        job_id = job_info["job_id"]

        logger.info(
            f"[FIX ENGINE] Starting fix for {error_type} error "
            f"(pipeline: {pipeline_id}, job: {job_id}, attempt: {attempt_number})"
        )

        # Step 1: Check memory FIRST (avoid redundant API calls)
        past_fix = self.memory.get_past_fix(error_type, error_message)

        if past_fix:
            logger.info(
                f"[MEMORY HIT] Found successful past fix for this error "
                f"(from pipeline #{past_fix['pipeline_id']})"
            )
            print(
                f"\n[MEMORY HIT] This exact error was fixed before!\n"
                f"  Previous pipeline: #{past_fix['pipeline_id']}\n"
                f"  Strategy used: {past_fix['fix_strategy']}\n"
                f"  Applying same fix without calling AI API...\n"
            )

            # Apply the same fix strategy
            fix_result = self._apply_remembered_fix(past_fix, error_info, repo_path, cleaned_logs)

            if fix_result.get("success"):
                return {
                    "success": True,
                    "fix_result": fix_result,
                    "validation_result": {"valid": True, "reason": "Memory-based fix"},
                    "used_memory": True
                }

        # Step 2: Handle unknown error type
        if error_type == "unknown":
            logger.warning("[FIX ENGINE] Unknown error type - cannot auto-fix")
            print(
                f"\n[MANUAL ACTION REQUIRED] Unknown error type detected.\n"
                f"The agent cannot fix this automatically.\n"
                f"Error: {error_message}\n"
                f"Please review logs manually at: {job_info.get('web_url', 'N/A')}\n"
            )
            return {
                "success": False,
                "fix_result": {
                    "success": False,
                    "fix_applied": "Unknown error type - manual review required",
                    "file_modified": None,
                    "strategy": "unknown_error"
                },
                "validation_result": None,
                "used_memory": False
            }

        # Step 3: Call appropriate fixer
        fix_result = self._call_fixer(error_type, error_info, repo_path, cleaned_logs)

        if not fix_result.get("success"):
            logger.error(f"[FIX ENGINE] Fix failed: {fix_result.get('fix_applied')}")
            return {
                "success": False,
                "fix_result": fix_result,
                "validation_result": None,
                "used_memory": False
            }

        # Step 4: Validate the fix
        file_modified = fix_result.get("file_modified")
        language = error_info.get("language", "unknown")

        if file_modified:
            validation_result = self.validator.validate_fix(file_modified, language)

            if not validation_result["valid"]:
                logger.error(
                    f"[FIX INVALID] Validation failed: {validation_result['reason']}"
                )
                print(
                    f"\n[FIX INVALID] The generated fix failed validation.\n"
                    f"  Reason: {validation_result['reason']}\n"
                    f"  Validator: {validation_result['validator_used']}\n"
                    f"  This fix will NOT be committed.\n"
                )
                return {
                    "success": False,
                    "fix_result": fix_result,
                    "validation_result": validation_result,
                    "used_memory": False
                }

            logger.info("[FIX ENGINE] Validation passed!")
        else:
            validation_result = {"valid": True, "reason": "No file to validate"}

        # Step 5: Save to memory
        self.memory.save_fix(
            pipeline_id=pipeline_id,
            job_id=job_id,
            error_type=error_type,
            error_message=error_message,
            fix_applied=fix_result["fix_applied"],
            fix_strategy=fix_result["strategy"],
            error_file=error_info.get("error_file"),
            pipeline_passed=False,  # Will be updated later
            attempt_number=attempt_number
        )

        logger.info("[FIX ENGINE] Fix completed and saved to memory")

        return {
            "success": True,
            "fix_result": fix_result,
            "validation_result": validation_result,
            "used_memory": False
        }

    def _call_fixer(
        self,
        error_type: str,
        error_info: dict,
        repo_path: str,
        cleaned_logs: str
    ) -> dict:
        """
        Route to the appropriate fixer based on error type.

        Args:
            error_type: Type of error
            error_info: Error details
            repo_path: Repository path
            cleaned_logs: Job logs

        Returns:
            Fix result dict
        """
        if error_type == "dependency":
            logger.info("[FIX ENGINE] Calling dependency fixer")
            return self.dependency_fixer.fix_dependency(error_info, repo_path)

        elif error_type == "syntax":
            logger.info("[FIX ENGINE] Calling syntax fixer (OpenAI)")
            return self.syntax_fixer.fix_syntax(error_info, repo_path)

        elif error_type == "test":
            logger.info("[FIX ENGINE] Calling test fixer (OpenAI)")
            return self.test_fixer.fix_test(error_info, repo_path, cleaned_logs)

        elif error_type == "config":
            logger.info("[FIX ENGINE] Calling config fixer (OpenAI)")
            return self.config_fixer.fix_config(error_info, repo_path, cleaned_logs)

        else:
            return {
                "success": False,
                "fix_applied": f"No fixer available for type: {error_type}",
                "file_modified": None,
                "strategy": "no_fixer"
            }

    def _apply_remembered_fix(
        self,
        past_fix: dict,
        error_info: dict,
        repo_path: str,
        cleaned_logs: str
    ) -> dict:
        """
        Apply a fix from memory (same strategy as before).

        Args:
            past_fix: Past fix record from memory
            error_info: Current error info
            repo_path: Repository path
            cleaned_logs: Job logs

        Returns:
            Fix result dict
        """
        strategy = past_fix["fix_strategy"]

        # Route to the same fixer that worked before
        if "dependency" in strategy or "manifest" in strategy:
            return self.dependency_fixer.fix_dependency(error_info, repo_path)

        elif "syntax" in strategy:
            return self.syntax_fixer.fix_syntax(error_info, repo_path)

        elif "test" in strategy:
            return self.test_fixer.fix_test(error_info, repo_path, cleaned_logs)

        elif "config" in strategy:
            return self.config_fixer.fix_config(error_info, repo_path, cleaned_logs)

        else:
            # Unknown strategy, fall back to normal flow
            return {
                "success": False,
                "fix_applied": "Could not apply remembered fix - unknown strategy",
                "file_modified": None,
                "strategy": "memory_fallback_failed"
            }


if __name__ == "__main__":
    # Test fix engine
    import sys
    import tempfile
    sys.path.insert(0, "..")

    from config import load_config

    try:
        config = load_config()
        memory = FixMemory("test_fix_engine.db")
        engine = FixEngine(config, memory)

        # Test dependency fix
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create requirements.txt
            req_file = f"{tmpdir}/requirements.txt"
            with open(req_file, 'w') as f:
                f.write("requests==2.28.0\n")

            error_info = {
                "error_type": "dependency",
                "error_message": "ModuleNotFoundError: No module named 'numpy'",
                "package_name": "numpy",
                "language": "python"
            }

            job_info = {
                "job_id": "12345",
                "job_name": "test-job"
            }

            result = engine.run_fix(
                pipeline_id="67890",
                job_info=job_info,
                error_info=error_info,
                repo_path=tmpdir,
                cleaned_logs="",
                attempt_number=1
            )

            print(f"Test result: {result}")

        # Clean up test database
        import os
        from pathlib import Path
        Path("test_fix_engine.db").unlink(missing_ok=True)

    except SystemExit:
        print("Configuration error - cannot test fix engine")
