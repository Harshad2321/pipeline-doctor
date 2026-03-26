"""
Test failure fixer using OpenAI API.
Fixes failing test assertions based on error logs.
"""

import os
import re

from loguru import logger
from openai import OpenAI, OpenAIError

from config import Config
from prompts.fix_prompts import TEST_FIX_SYSTEM, TEST_FIX_USER, strip_markdown_fences


class TestFixer:
    """Fixes failing tests using OpenAI API."""

    def __init__(self, config: Config):
        """
        Initialize test fixer with OpenAI client.

        Args:
            config: Configuration with OpenAI credentials
        """
        self.config = config
        self.client = OpenAI(api_key=config.openai_api_key)

    def fix_test(self, error_info: dict, repo_path: str, cleaned_logs: str) -> dict:
        """
        Fix failing test using OpenAI API.

        Args:
            error_info: Error information
            repo_path: Path to repository root
            cleaned_logs: Cleaned pipeline logs for context

        Returns:
            Dict with success, fix_applied, file_modified, strategy
        """
        error_message = error_info.get("error_message")
        language = error_info.get("language", "python")

        # Try to extract test file from error info or logs
        test_file = error_info.get("error_file")

        if not test_file:
            test_file = self._extract_test_file_from_logs(cleaned_logs, language)

        if not test_file:
            logger.error("[TEST FIXER] Could not identify test file")
            print(
                f"\n[MANUAL ACTION REQUIRED] Could not find test file in logs.\n"
                f"Please check {repo_path}/tests/ manually and fix the failing test.\n"
                f"Error: {error_message}\n"
            )
            return {
                "success": False,
                "fix_applied": "Could not identify test file",
                "file_modified": None,
                "strategy": "test_fix_failed"
            }

        # Construct full file path
        file_path = os.path.join(repo_path, test_file)

        # Check if file exists
        if not os.path.exists(file_path):
            logger.error(f"[TEST FIXER] Test file not found: {file_path}")
            print(
                f"\n[MANUAL ACTION REQUIRED] Test file not found: {test_file}\n"
                f"Full path: {file_path}\n"
            )
            return {
                "success": False,
                "fix_applied": f"Test file not found: {test_file}",
                "file_modified": None,
                "strategy": "test_fix_failed"
            }

        # Read test code
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                test_code = f.read()
        except Exception as e:
            logger.error(f"[TEST FIXER] Failed to read test file {file_path}: {e}")
            return {
                "success": False,
                "fix_applied": f"Failed to read test file: {e}",
                "file_modified": None,
                "strategy": "test_fix_failed"
            }

        logger.info(f"[TEST FIXER] Fixing test in {test_file} using {self.config.openai_model}")

        # Extract relevant logs (keep it concise for API)
        relevant_logs = self._extract_relevant_test_logs(cleaned_logs, test_file)

        # Call OpenAI API
        try:
            response = self.client.chat.completions.create(
                model=self.config.openai_model,
                max_tokens=4096,
                temperature=0,  # Deterministic for code fixes
                messages=[
                    {"role": "system", "content": TEST_FIX_SYSTEM},
                    {"role": "user", "content": TEST_FIX_USER.format(
                        language=language,
                        error_message=error_message,
                        test_file=test_file,
                        test_code=test_code,
                        relevant_logs=relevant_logs
                    )}
                ]
            )

            fixed_code = response.choices[0].message.content.strip()

            if not fixed_code:
                logger.error("[TEST FIXER] OpenAI returned empty response")
                return {
                    "success": False,
                    "fix_applied": "OpenAI returned empty response",
                    "file_modified": None,
                    "strategy": "test_fix_failed"
                }

            # Strip markdown fences if present
            fixed_code = strip_markdown_fences(fixed_code)

            # Write fixed code back to file
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(fixed_code)

                logger.info(f"[TEST FIXER] Successfully fixed {test_file}")
                return {
                    "success": True,
                    "fix_applied": f"Fixed failing test in {test_file}",
                    "file_modified": file_path,
                    "original_code": test_code,
                    "fixed_code": fixed_code,
                    "strategy": "openai_test_fix"
                }

            except Exception as e:
                logger.error(f"[TEST FIXER] Failed to write fixed code: {e}")
                return {
                    "success": False,
                    "fix_applied": f"Failed to write fixed code: {e}",
                    "file_modified": None,
                    "strategy": "test_fix_failed"
                }

        except OpenAIError as e:
            logger.error(f"[TEST FIXER] OpenAI API error: {e}")
            return {
                "success": False,
                "fix_applied": f"OpenAI API error: {e}",
                "file_modified": None,
                "strategy": "test_fix_failed"
            }

        except Exception as e:
            logger.error(f"[TEST FIXER] Unexpected error: {e}")
            return {
                "success": False,
                "fix_applied": f"Unexpected error: {e}",
                "file_modified": None,
                "strategy": "test_fix_failed"
            }

    def _extract_test_file_from_logs(self, logs: str, language: str) -> str:
        """
        Extract test file path from logs.

        Args:
            logs: Cleaned logs
            language: Programming language

        Returns:
            Test file path or None
        """
        if language == "python":
            # Look for patterns like: tests/test_api.py::test_function
            patterns = [
                r"(tests?/[a-zA-Z0-9_/]+test_[a-zA-Z0-9_]+\.py)",
                r"([a-zA-Z0-9_/]+test_[a-zA-Z0-9_]+\.py)",
                r"(test[a-zA-Z0-9_/]+\.py)"
            ]
        elif language == "node":
            patterns = [
                r"(tests?/[a-zA-Z0-9_/]+\.test\.[jt]s)",
                r"(tests?/[a-zA-Z0-9_/]+\.spec\.[jt]s)",
                r"([a-zA-Z0-9_/]+\.test\.[jt]s)"
            ]
        else:
            # Generic pattern
            patterns = [r"(tests?/[a-zA-Z0-9_/]+\.[a-z]+)"]

        for pattern in patterns:
            match = re.search(pattern, logs)
            if match:
                return match.group(1)

        return None

    def _extract_relevant_test_logs(self, logs: str, test_file: str) -> str:
        """
        Extract only the relevant portion of logs related to the test.

        Args:
            logs: Full cleaned logs
            test_file: Test file name

        Returns:
            Relevant log excerpt
        """
        lines = logs.split('\n')
        relevant = []
        capture = False

        for line in lines:
            # Start capturing when we see the test file
            if test_file in line:
                capture = True

            if capture:
                relevant.append(line)

                # Stop after capturing enough context
                if len(relevant) > 50:
                    break

        if relevant:
            return '\n'.join(relevant)

        # If no specific section found, return last 30 lines
        return '\n'.join(lines[-30:])
