"""
Classifies errors from pipeline logs into structured categories.
Uses pattern matching to identify error types and extract relevant context.
"""

import re
from typing import Optional

from loguru import logger


class ErrorClassifier:
    """Classifies pipeline errors into actionable categories."""

    # Error type patterns (checked in priority order)
    DEPENDENCY_PATTERNS = [
        r"ModuleNotFoundError",
        r"No module named ['\"]([^'\"]+)['\"]",
        r"Cannot find module ['\"]([^'\"]+)['\"]",
        r"ImportError",
        r"npm ERR! 404.*not found",
        r"Package .* not found",
        r"error: package .* not found",
        r"unable to resolve dependency"
    ]

    SYNTAX_PATTERNS = [
        r"SyntaxError",
        r"IndentationError",
        r"ParseError",
        r"unexpected token",
        r"invalid syntax",
        r"unterminated string",
        r"expected.*but found",
    ]

    TEST_PATTERNS = [
        r"AssertionError",
        r"FAILED.*test_",
        r"assert .* ==",
        r"Expected.*but got",
        r"\d+ failed,.*test",
        r"Test.*failed",
        r"pytest.*FAILED"
    ]

    CONFIG_PATTERNS = [
        r"yaml\.scanner",
        r"Invalid configuration",
        r"\.gitlab-ci\.yml",
        r"pipeline.*not valid",
        r"Job.*not defined",
        r"stage.*does not exist"
    ]

    def classify_error(self, cleaned_logs: str, job_info: dict) -> dict:
        """
        Classify error type from logs and extract structured information.

        Args:
            cleaned_logs: Cleaned log content
            job_info: Job metadata (job_id, job_name, stage, etc.)

        Returns:
            Dict with structured error information:
                - error_type: dependency|syntax|test|config|unknown
                - confidence: 0.0-1.0
                - error_message: exact error line
                - error_file: path/to/file.py or None
                - error_line: line number or None
                - package_name: package for dependency errors or None
                - language: python|node|go|java|unknown
                - stage: from job_info
                - raw_indicators: list of matched keywords
        """
        logger.info(f"[CLASSIFIER] Classifying error for job {job_info.get('job_name', 'unknown')}")

        # Extract error message (most relevant line)
        error_message = self._extract_error_message(cleaned_logs)

        # Classify error type
        error_type, confidence, raw_indicators, package_name = self._classify_type(cleaned_logs)

        # Extract file and line number
        error_file, error_line = self._extract_file_location(cleaned_logs)

        # Detect language
        language = self._detect_language(cleaned_logs, error_file)

        result = {
            "error_type": error_type,
            "confidence": confidence,
            "error_message": error_message,
            "error_file": error_file,
            "error_line": error_line,
            "package_name": package_name,
            "language": language,
            "stage": job_info.get("stage", "unknown"),
            "raw_indicators": raw_indicators
        }

        logger.info(
            f"[CLASSIFIER] Error type: {error_type} "
            f"(confidence: {confidence:.2f}, language: {language})"
        )

        return result

    def _classify_type(self, logs: str) -> tuple[str, float, list[str], Optional[str]]:
        """
        Classify the error type based on pattern matching.

        Returns:
            (error_type, confidence, raw_indicators, package_name)
        """
        # Check dependency errors
        for pattern in self.DEPENDENCY_PATTERNS:
            match = re.search(pattern, logs, re.IGNORECASE)
            if match:
                package_name = None
                if match.groups():
                    package_name = match.group(1)
                else:
                    # Try to extract package name from context
                    package_name = self._extract_package_name(logs)

                return "dependency", 0.95, ["dependency"], package_name

        # Check syntax errors
        for pattern in self.SYNTAX_PATTERNS:
            if re.search(pattern, logs, re.IGNORECASE):
                return "syntax", 0.90, ["syntax"], None

        # Check test errors
        for pattern in self.TEST_PATTERNS:
            if re.search(pattern, logs, re.IGNORECASE):
                return "test", 0.85, ["test"], None

        # Check config errors
        for pattern in self.CONFIG_PATTERNS:
            if re.search(pattern, logs, re.IGNORECASE):
                return "config", 0.80, ["config"], None

        # Unknown error type
        return "unknown", 0.30, ["unknown"], None

    def _extract_error_message(self, logs: str) -> str:
        """
        Extract the most relevant error message line from logs.

        Returns:
            The key error message line
        """
        error_keywords = [
            "Error:",
            "ERROR:",
            "Failed:",
            "FAILED:",
            "Exception:",
            "Traceback",
            "AssertionError"
        ]

        lines = logs.split('\n')

        # Find first line with error keyword
        for line in lines:
            for keyword in error_keywords:
                if keyword in line:
                    # Clean and return
                    return line.strip()[:500]  # Limit length

        # If no clear error, return last non-empty line
        for line in reversed(lines):
            if line.strip():
                return line.strip()[:500]

        return "Unknown error - check logs"

    def _extract_file_location(self, logs: str) -> tuple[Optional[str], Optional[int]]:
        """
        Extract file path and line number from logs.

        Returns:
            (file_path, line_number) or (None, None)
        """
        # Common patterns for file locations
        patterns = [
            r'File "([^"]+)", line (\d+)',  # Python traceback
            r"([a-zA-Z0-9_/\.\-]+\.py):(\d+):",  # Python error
            r"([a-zA-Z0-9_/\.\-]+\.js):(\d+):",  # JavaScript error
            r"([a-zA-Z0-9_/\.\-]+\.go):(\d+):",  # Go error
            r"([a-zA-Z0-9_/\.\-]+\.java):(\d+):",  # Java error
            r"at ([a-zA-Z0-9_/\.\-]+):(\d+):"  # Generic
        ]

        for pattern in patterns:
            match = re.search(pattern, logs)
            if match:
                file_path = match.group(1)
                line_number = int(match.group(2))
                return file_path, line_number

        return None, None

    def _extract_package_name(self, logs: str) -> Optional[str]:
        """
        Try to extract package/module name from dependency error logs.

        Returns:
            Package name or None
        """
        # Python import patterns
        python_patterns = [
            r"No module named ['\"]([^'\"]+)['\"]",
            r"ModuleNotFoundError:.*['\"]([^'\"]+)['\"]",
            r"import ([a-zA-Z0-9_]+)"
        ]

        for pattern in python_patterns:
            match = re.search(pattern, logs)
            if match:
                package = match.group(1).split('.')[0]  # Get root package
                return package

        # Node.js patterns
        node_patterns = [
            r"Cannot find module ['\"]([^'\"]+)['\"]",
            r"npm ERR! 404.*'([^']+)'",
        ]

        for pattern in node_patterns:
            match = re.search(pattern, logs)
            if match:
                return match.group(1)

        return None

    def _detect_language(self, logs: str, error_file: Optional[str]) -> str:
        """
        Detect programming language from logs or file extension.

        Returns:
            Language identifier: python|node|go|java|unknown
        """
        # Check file extension first
        if error_file:
            if error_file.endswith('.py'):
                return "python"
            elif error_file.endswith('.js') or error_file.endswith('.ts'):
                return "node"
            elif error_file.endswith('.go'):
                return "go"
            elif error_file.endswith('.java'):
                return "java"

        # Check logs for language indicators
        language_indicators = {
            "python": ["python", "pip", "pytest", "Python", "venv"],
            "node": ["npm", "node", "javascript", "yarn", "package.json"],
            "go": ["go build", "go test", "golang"],
            "java": ["java", "javac", "maven", "gradle"]
        }

        for lang, indicators in language_indicators.items():
            if any(indicator in logs for indicator in indicators):
                return lang

        return "unknown"
