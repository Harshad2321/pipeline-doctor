"""
Validates fixes before committing them.
Checks syntax for Python, JavaScript, YAML, etc.
"""

import os
import subprocess

import yaml
from loguru import logger


class FixValidator:
    """Validates fixed code before committing."""

    def validate_fix(self, file_path: str, language: str) -> dict:
        """
        Validate a fixed file based on its language.

        Args:
            file_path: Path to the fixed file
            language: Programming language (python, node, yaml, etc.)

        Returns:
            Dict with valid (bool), reason (str), validator_used (str)
        """
        if not os.path.exists(file_path):
            return {
                "valid": False,
                "reason": f"File not found: {file_path}",
                "validator_used": "none"
            }

        logger.info(f"[VALIDATOR] Validating {file_path} as {language}")

        # Route to appropriate validator
        if language == "python":
            return self._validate_python(file_path)
        elif language == "node" or language == "javascript":
            return self._validate_javascript(file_path)
        elif language == "yaml" or file_path.endswith(".yml"):
            return self._validate_yaml(file_path)
        elif language == "go":
            return self._validate_go(file_path)
        else:
            logger.warning(f"[VALIDATOR] No validator for language: {language}")
            return {
                "valid": True,  # Assume valid if we can't validate
                "reason": f"No validator available for {language}",
                "validator_used": "none"
            }

    def _validate_python(self, file_path: str) -> dict:
        """
        Validate Python syntax using py_compile.

        Args:
            file_path: Path to Python file

        Returns:
            Validation result dict
        """
        try:
            # Use Python's built-in syntax checker
            result = subprocess.run(
                ["python", "-m", "py_compile", file_path],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                logger.info(f"[VALIDATOR] Python syntax validation passed: {file_path}")
                return {
                    "valid": True,
                    "reason": "Python syntax check passed",
                    "validator_used": "py_compile"
                }
            else:
                error_msg = result.stderr.strip()
                logger.error(f"[VALIDATOR] Python syntax validation failed: {error_msg}")
                return {
                    "valid": False,
                    "reason": f"Python syntax error: {error_msg}",
                    "validator_used": "py_compile"
                }

        except subprocess.TimeoutExpired:
            return {
                "valid": False,
                "reason": "Validation timeout",
                "validator_used": "py_compile"
            }

        except Exception as e:
            logger.error(f"[VALIDATOR] Python validation error: {e}")
            return {
                "valid": False,
                "reason": f"Validation error: {e}",
                "validator_used": "py_compile"
            }

    def _validate_javascript(self, file_path: str) -> dict:
        """
        Validate JavaScript syntax using node --check.

        Args:
            file_path: Path to JavaScript file

        Returns:
            Validation result dict
        """
        try:
            # Check if Node.js is installed
            which_result = subprocess.run(
                ["which", "node"],
                capture_output=True,
                timeout=5
            )

            if which_result.returncode != 0:
                logger.warning("[VALIDATOR] Node.js not found - skipping JS validation")
                print(
                    f"\n[MANUAL ACTION REQUIRED] Node.js not installed.\n"
                    f"Cannot validate JavaScript fix for {file_path}.\n"
                    f"Install Node.js from https://nodejs.org to enable JS validation.\n"
                )
                return {
                    "valid": True,  # Skip validation
                    "reason": "skipped - node not found",
                    "validator_used": "none"
                }

            # Validate with node --check
            result = subprocess.run(
                ["node", "--check", file_path],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                logger.info(f"[VALIDATOR] JavaScript syntax validation passed: {file_path}")
                return {
                    "valid": True,
                    "reason": "JavaScript syntax check passed",
                    "validator_used": "node --check"
                }
            else:
                error_msg = result.stderr.strip()
                logger.error(f"[VALIDATOR] JavaScript syntax validation failed: {error_msg}")
                return {
                    "valid": False,
                    "reason": f"JavaScript syntax error: {error_msg}",
                    "validator_used": "node --check"
                }

        except Exception as e:
            logger.error(f"[VALIDATOR] JavaScript validation error: {e}")
            return {
                "valid": False,
                "reason": f"Validation error: {e}",
                "validator_used": "node --check"
            }

    def _validate_yaml(self, file_path: str) -> dict:
        """
        Validate YAML syntax using PyYAML.

        Args:
            file_path: Path to YAML file

        Returns:
            Validation result dict
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                yaml.safe_load(f)

            logger.info(f"[VALIDATOR] YAML validation passed: {file_path}")
            return {
                "valid": True,
                "reason": "YAML syntax check passed",
                "validator_used": "pyyaml"
            }

        except yaml.YAMLError as e:
            error_msg = str(e)
            logger.error(f"[VALIDATOR] YAML validation failed: {error_msg}")
            return {
                "valid": False,
                "reason": f"YAML syntax error: {error_msg}",
                "validator_used": "pyyaml"
            }

        except Exception as e:
            logger.error(f"[VALIDATOR] YAML validation error: {e}")
            return {
                "valid": False,
                "reason": f"Validation error: {e}",
                "validator_used": "pyyaml"
            }

    def _validate_go(self, file_path: str) -> dict:
        """
        Validate Go syntax using go fmt.

        Args:
            file_path: Path to Go file

        Returns:
            Validation result dict
        """
        try:
            # Check if Go is installed
            which_result = subprocess.run(
                ["which", "go"],
                capture_output=True,
                timeout=5
            )

            if which_result.returncode != 0:
                logger.warning("[VALIDATOR] Go not found - skipping Go validation")
                return {
                    "valid": True,  # Skip validation
                    "reason": "skipped - go not found",
                    "validator_used": "none"
                }

            # Validate with go fmt
            result = subprocess.run(
                ["go", "fmt", file_path],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                logger.info(f"[VALIDATOR] Go syntax validation passed: {file_path}")
                return {
                    "valid": True,
                    "reason": "Go syntax check passed",
                    "validator_used": "go fmt"
                }
            else:
                error_msg = result.stderr.strip()
                logger.error(f"[VALIDATOR] Go validation failed: {error_msg}")
                return {
                    "valid": False,
                    "reason": f"Go syntax error: {error_msg}",
                    "validator_used": "go fmt"
                }

        except Exception as e:
            logger.error(f"[VALIDATOR] Go validation error: {e}")
            return {
                "valid": False,
                "reason": f"Validation error: {e}",
                "validator_used": "go fmt"
            }
