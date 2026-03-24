"""
Unit tests for error classifier.
"""

import pytest
from agent.classifier import ErrorClassifier


def test_classify_dependency_error():
    """Test classification of dependency errors."""
    classifier = ErrorClassifier()

    log = """
    Traceback (most recent call last):
      File "main.py", line 5, in <module>
        import numpy
    ModuleNotFoundError: No module named 'numpy'
    """

    job_info = {"job_name": "test", "stage": "test"}
    result = classifier.classify_error(log, job_info)

    assert result["error_type"] == "dependency"
    assert result["package_name"] == "numpy"
    assert result["language"] == "python"
    assert result["confidence"] > 0.9


def test_classify_syntax_error():
    """Test classification of syntax errors."""
    classifier = ErrorClassifier()

    log = """
      File "app.py", line 42
        def hello()
                  ^
    SyntaxError: invalid syntax
    """

    job_info = {"job_name": "test", "stage": "test"}
    result = classifier.classify_error(log, job_info)

    assert result["error_type"] == "syntax"
    assert result["error_file"] == "app.py"
    assert result["error_line"] == 42
    assert result["confidence"] > 0.8


def test_classify_test_error():
    """Test classification of test failures."""
    classifier = ErrorClassifier()

    log = """
    FAILED tests/test_api.py::test_user_creation - AssertionError: Expected 201 but got 400
    """

    job_info = {"job_name": "test", "stage": "test"}
    result = classifier.classify_error(log, job_info)

    assert result["error_type"] == "test"
    assert result["confidence"] > 0.8


def test_classify_config_error():
    """Test classification of config errors."""
    classifier = ErrorClassifier()

    log = """
    yaml.scanner.ScannerError: mapping values are not allowed here
      in ".gitlab-ci.yml", line 5, column 10
    """

    job_info = {"job_name": "test", "stage": "test"}
    result = classifier.classify_error(log, job_info)

    assert result["error_type"] == "config"
    assert result["confidence"] > 0.7


def test_classify_unknown_error():
    """Test classification of unknown errors."""
    classifier = ErrorClassifier()

    log = """
    Some random error that doesn't match any pattern
    """

    job_info = {"job_name": "test", "stage": "test"}
    result = classifier.classify_error(log, job_info)

    assert result["error_type"] == "unknown"
    assert result["confidence"] < 0.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
