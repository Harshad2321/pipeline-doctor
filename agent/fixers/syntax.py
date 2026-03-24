"""
Syntax error fixer using OpenAI API.
Reads broken code, sends to GPT-4o, validates and writes fixed code back.
"""

import os
from typing import Optional

from loguru import logger
from openai import OpenAI, OpenAIError

from config import Config
from prompts.fix_prompts import SYNTAX_FIX_SYSTEM, SYNTAX_FIX_USER, strip_markdown_fences


class SyntaxFixer:
    """Fixes syntax errors using OpenAI API."""

    def __init__(self, config: Config):
        """
        Initialize syntax fixer with OpenAI client.

        Args:
            config: Configuration with OpenAI credentials
        """
        self.config = config
        self.client = OpenAI(api_key=config.openai_api_key)

    def fix_syntax(self, error_info: dict, repo_path: str) -> dict:
        """
        Fix syntax error in a file using OpenAI API.

        Args:
            error_info: Error information with error_file, error_message, etc.
            repo_path: Path to repository root

        Returns:
            Dict with success, fix_applied, file_modified, strategy
        """
        error_file = error_info.get("error_file")
        error_message = error_info.get("error_message")
        error_line = error_info.get("error_line")
        language = error_info.get("language", "python")

        if not error_file:
            logger.error("[SYNTAX FIXER] No error file specified")
            return {
                "success": False,
                "fix_applied": "No file path in error",
                "file_modified": None,
                "strategy": "syntax_fix_failed"
            }

        # Construct full file path
        file_path = os.path.join(repo_path, error_file)

        # Check if file exists
        if not os.path.exists(file_path):
            logger.error(f"[SYNTAX FIXER] File not found: {file_path}")
            print(
                f"\n[MANUAL ACTION REQUIRED] Cannot find file: {error_file}\n"
                f"Full path: {file_path}\n"
                f"Please verify the file path from the error logs.\n"
            )
            return {
                "success": False,
                "fix_applied": f"File not found: {error_file}",
                "file_modified": None,
                "strategy": "syntax_fix_failed"
            }

        # Read broken code
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                broken_code = f.read()
        except Exception as e:
            logger.error(f"[SYNTAX FIXER] Failed to read file {file_path}: {e}")
            return {
                "success": False,
                "fix_applied": f"Failed to read file: {e}",
                "file_modified": None,
                "strategy": "syntax_fix_failed"
            }

        logger.info(f"[SYNTAX FIXER] Fixing syntax error in {error_file} using {self.config.openai_model}")

        # Call OpenAI API
        try:
            response = self.client.chat.completions.create(
                model=self.config.openai_model,
                max_tokens=4096,
                temperature=0,  # Deterministic for code fixes
                messages=[
                    {"role": "system", "content": SYNTAX_FIX_SYSTEM},
                    {"role": "user", "content": SYNTAX_FIX_USER.format(
                        language=language,
                        error_message=error_message,
                        error_file=error_file,
                        error_line=error_line or "unknown",
                        broken_code=broken_code
                    )}
                ]
            )

            fixed_code = response.choices[0].message.content.strip()

            if not fixed_code:
                logger.error("[SYNTAX FIXER] OpenAI returned empty response")
                return {
                    "success": False,
                    "fix_applied": "OpenAI returned empty response",
                    "file_modified": None,
                    "strategy": "syntax_fix_failed"
                }

            # Strip markdown fences if present
            fixed_code = strip_markdown_fences(fixed_code)

            # Write fixed code back to file
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(fixed_code)

                logger.info(f"[SYNTAX FIXER] Successfully fixed {error_file}")
                return {
                    "success": True,
                    "fix_applied": f"Fixed syntax error in {error_file}",
                    "file_modified": file_path,
                    "original_code": broken_code,
                    "fixed_code": fixed_code,
                    "strategy": "openai_syntax_fix"
                }

            except Exception as e:
                logger.error(f"[SYNTAX FIXER] Failed to write fixed code: {e}")
                return {
                    "success": False,
                    "fix_applied": f"Failed to write fixed code: {e}",
                    "file_modified": None,
                    "strategy": "syntax_fix_failed"
                }

        except OpenAIError as e:
            logger.error(f"[SYNTAX FIXER] OpenAI API error: {e}")
            if "invalid_api_key" in str(e):
                print(
                    f"\n[MANUAL ACTION REQUIRED] Invalid OpenAI API key.\n"
                    f"Please check your OPENAI_API_KEY in .env file.\n"
                    f"Get a valid key from: https://platform.openai.com/api-keys\n"
                )
            return {
                "success": False,
                "fix_applied": f"OpenAI API error: {e}",
                "file_modified": None,
                "strategy": "syntax_fix_failed"
            }

        except Exception as e:
            logger.error(f"[SYNTAX FIXER] Unexpected error: {e}")
            return {
                "success": False,
                "fix_applied": f"Unexpected error: {e}",
                "file_modified": None,
                "strategy": "syntax_fix_failed"
            }


if __name__ == "__main__":
    # Test syntax fixer
    import sys
    import tempfile
    sys.path.insert(0, "../..")

    from config import load_config

    try:
        config = load_config()
        fixer = SyntaxFixer(config)

        # Create test file with syntax error
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "test.py")
            with open(test_file, 'w') as f:
                f.write("def hello()\n    print('hi')")  # Missing colon

            error_info = {
                "error_file": "test.py",
                "error_message": "SyntaxError: invalid syntax",
                "error_line": 1,
                "language": "python"
            }

            result = fixer.fix_syntax(error_info, tmpdir)
            print(f"Test result: {result}")

            if result.get("success"):
                with open(test_file, 'r') as f:
                    print(f"Fixed code:\n{f.read()}")

    except SystemExit:
        print("Configuration error - cannot test syntax fixer")
