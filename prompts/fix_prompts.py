"""
OpenAI prompt templates for different fix types.
All prompts are structured with clear system and user messages for GPT-4o.
"""

# ============================================================================
# SYNTAX FIX PROMPTS
# ============================================================================

SYNTAX_FIX_SYSTEM = """You are an expert code repair tool.
You receive broken code and an error message.
You return ONLY the fixed code — no explanation, no markdown fences, no comments about what you changed.
The output must be valid, runnable code in the same language as the input."""

SYNTAX_FIX_USER = """Fix the syntax error in the following {language} code.

ERROR MESSAGE:
{error_message}

FILE: {error_file}
LINE: {error_line}

BROKEN CODE:
{broken_code}

Return ONLY the complete fixed code. Nothing else."""


# ============================================================================
# TEST FIX PROMPTS
# ============================================================================

TEST_FIX_SYSTEM = """You are an expert test repair tool.
You receive a failing test file, the error message, and pipeline logs.
You return ONLY the fixed test file — no explanation, no markdown fences.
Fix only the failing assertion. Do NOT change the function being tested."""

TEST_FIX_USER = """Fix the failing test in the following {language} test file.

ERROR MESSAGE:
{error_message}

TEST FILE: {test_file}

TEST CODE:
{test_code}

PIPELINE LOGS (relevant section):
{relevant_logs}

Return ONLY the complete fixed test file. Nothing else."""


# ============================================================================
# CONFIG FIX PROMPTS
# ============================================================================

CONFIG_FIX_SYSTEM = """You are an expert GitLab CI/CD configuration repair tool.
You receive a broken .gitlab-ci.yml and the error message.
You return ONLY the fixed valid YAML — no explanation, no markdown fences.
Fix only the broken part. Do not restructure the entire file."""

CONFIG_FIX_USER = """Fix the GitLab CI configuration error.

ERROR MESSAGE:
{error_message}

CONFIG FILE CONTENT:
{config_content}

PIPELINE LOGS (relevant section):
{relevant_logs}

Return ONLY the complete fixed YAML. Nothing else."""


# ============================================================================
# HELPER FUNCTION TO STRIP MARKDOWN FENCES
# ============================================================================

def strip_markdown_fences(code: str) -> str:
    """
    Remove markdown code fences if present (sometimes AI adds them despite instructions).

    Args:
        code: Code that might have ```language or ``` fences

    Returns:
        Clean code without fences
    """
    code = code.strip()

    # Remove opening fence
    if code.startswith('```'):
        lines = code.split('\n')
        lines = lines[1:]  # Remove first line with ```language
        code = '\n'.join(lines)

    # Remove closing fence
    if code.endswith('```'):
        lines = code.split('\n')
        lines = lines[:-1]  # Remove last line with ```
        code = '\n'.join(lines)

    return code.strip()


if __name__ == "__main__":
    # Test prompt formatting
    print("=== Syntax Fix Prompt ===")
    print(SYNTAX_FIX_USER.format(
        language="python",
        error_message="SyntaxError: invalid syntax",
        error_file="main.py",
        error_line=10,
        broken_code="def hello()\n    print('hi')"
    ))
    print()

    print("=== Test strip_markdown_fences ===")
    test_code = "```python\nprint('hello')\n```"
    print(f"Input: {test_code}")
    print(f"Output: {strip_markdown_fences(test_code)}")
