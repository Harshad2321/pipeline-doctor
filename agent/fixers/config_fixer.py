"""
GitLab CI configuration fixer using OpenAI API.
Fixes .gitlab-ci.yml errors and validates YAML before writing.
"""

import os

import yaml
from loguru import logger
from openai import OpenAI, OpenAIError

from config import Config
from prompts.fix_prompts import CONFIG_FIX_SYSTEM, CONFIG_FIX_USER, strip_markdown_fences


class ConfigFixer:
    """Fixes GitLab CI configuration errors using OpenAI API."""

    def __init__(self, config: Config):
        """
        Initialize config fixer with OpenAI client.

        Args:
            config: Configuration with OpenAI credentials
        """
        self.config = config
        self.client = OpenAI(api_key=config.openai_api_key)

    def fix_config(self, error_info: dict, repo_path: str, cleaned_logs: str) -> dict:
        """
        Fix .gitlab-ci.yml configuration error using OpenAI API.

        Args:
            error_info: Error information
            repo_path: Path to repository root
            cleaned_logs: Cleaned pipeline logs for context

        Returns:
            Dict with success, fix_applied, file_modified, strategy
        """
        error_message = error_info.get("error_message")

        # GitLab CI config is always .gitlab-ci.yml at repo root
        config_file = ".gitlab-ci.yml"
        file_path = os.path.join(repo_path, config_file)

        # Check if file exists
        if not os.path.exists(file_path):
            logger.error(f"[CONFIG FIXER] .gitlab-ci.yml not found in {repo_path}")
            print(
                f"\n[MANUAL ACTION REQUIRED] .gitlab-ci.yml not found in {repo_path}\n"
                f"Cannot fix GitLab CI configuration without the file.\n"
            )
            return {
                "success": False,
                "fix_applied": ".gitlab-ci.yml not found",
                "file_modified": None,
                "strategy": "config_fix_failed"
            }

        # Read config content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                config_content = f.read()
        except Exception as e:
            logger.error(f"[CONFIG FIXER] Failed to read .gitlab-ci.yml: {e}")
            return {
                "success": False,
                "fix_applied": f"Failed to read config file: {e}",
                "file_modified": None,
                "strategy": "config_fix_failed"
            }

        logger.info(f"[CONFIG FIXER] Fixing .gitlab-ci.yml using {self.config.openai_model}")

        # Extract relevant logs
        relevant_logs = self._extract_config_error_logs(cleaned_logs)

        # Call OpenAI API
        try:
            response = self.client.chat.completions.create(
                model=self.config.openai_model,
                max_tokens=4096,
                temperature=0,  # Deterministic for config fixes
                messages=[
                    {"role": "system", "content": CONFIG_FIX_SYSTEM},
                    {"role": "user", "content": CONFIG_FIX_USER.format(
                        error_message=error_message,
                        config_content=config_content,
                        relevant_logs=relevant_logs
                    )}
                ]
            )

            fixed_config = response.choices[0].message.content.strip()

            if not fixed_config:
                logger.error("[CONFIG FIXER] OpenAI returned empty response")
                return {
                    "success": False,
                    "fix_applied": "OpenAI returned empty response",
                    "file_modified": None,
                    "strategy": "config_fix_failed"
                }

            # Strip markdown fences if present
            fixed_config = strip_markdown_fences(fixed_config)

            # Validate YAML before writing
            try:
                yaml.safe_load(fixed_config)
                logger.info("[CONFIG FIXER] YAML validation passed")
            except yaml.YAMLError as e:
                logger.error(f"[CONFIG FIXER] OpenAI returned invalid YAML: {e}")
                print(
                    f"\n[WARNING] OpenAI returned invalid YAML.\n"
                    f"Skipping config fix and escalating to human review.\n"
                    f"YAML error: {e}\n"
                )
                return {
                    "success": False,
                    "fix_applied": f"OpenAI returned invalid YAML: {e}",
                    "file_modified": None,
                    "strategy": "config_fix_invalid_yaml"
                }

            # Write fixed config back to file
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(fixed_config)

                logger.info("[CONFIG FIXER] Successfully fixed .gitlab-ci.yml")
                return {
                    "success": True,
                    "fix_applied": "Fixed .gitlab-ci.yml configuration error",
                    "file_modified": file_path,
                    "original_config": config_content,
                    "fixed_config": fixed_config,
                    "strategy": "openai_config_fix"
                }

            except Exception as e:
                logger.error(f"[CONFIG FIXER] Failed to write fixed config: {e}")
                return {
                    "success": False,
                    "fix_applied": f"Failed to write fixed config: {e}",
                    "file_modified": None,
                    "strategy": "config_fix_failed"
                }

        except OpenAIError as e:
            logger.error(f"[CONFIG FIXER] OpenAI API error: {e}")
            return {
                "success": False,
                "fix_applied": f"OpenAI API error: {e}",
                "file_modified": None,
                "strategy": "config_fix_failed"
            }

        except Exception as e:
            logger.error(f"[CONFIG FIXER] Unexpected error: {e}")
            return {
                "success": False,
                "fix_applied": f"Unexpected error: {e}",
                "file_modified": None,
                "strategy": "config_fix_failed"
            }

    def _extract_config_error_logs(self, logs: str) -> str:
        """
        Extract relevant configuration error logs.

        Args:
            logs: Full cleaned logs

        Returns:
            Relevant log excerpt
        """
        lines = logs.split('\n')
        relevant = []

        # Look for lines mentioning config, yaml, or pipeline validation
        config_keywords = [
            ".gitlab-ci.yml",
            "configuration",
            "pipeline",
            "job",
            "stage",
            "yaml",
            "invalid"
        ]

        for line in lines:
            if any(keyword in line.lower() for keyword in config_keywords):
                relevant.append(line)

        if relevant:
            # Return last 40 relevant lines (most recent context)
            return '\n'.join(relevant[-40:])

        # If no specific config errors, return last 30 lines
        return '\n'.join(lines[-30:])


if __name__ == "__main__":
    # Test config fixer
    import sys
    import tempfile
    sys.path.insert(0, "../..")

    from config import load_config

    try:
        config = load_config()
        fixer = ConfigFixer(config)

        # Create test .gitlab-ci.yml with error
        with tempfile.TemporaryDirectory() as tmpdir:
            ci_file = os.path.join(tmpdir, ".gitlab-ci.yml")
            with open(ci_file, 'w') as f:
                f.write("""
stages
  - test
  - deploy

test-job:
  stage: test
  script:
    - echo "Testing"
""")  # Missing colon after 'stages'

            error_info = {
                "error_message": "yaml.scanner.ScannerError: mapping values are not allowed here"
            }

            logs = "Invalid configuration: .gitlab-ci.yml - mapping values are not allowed"

            result = fixer.fix_config(error_info, tmpdir, logs)
            print(f"Test result: {result}")

            if result.get("success"):
                with open(ci_file, 'r') as f:
                    print(f"Fixed config:\n{f.read()}")

    except SystemExit:
        print("Configuration error - cannot test config fixer")
