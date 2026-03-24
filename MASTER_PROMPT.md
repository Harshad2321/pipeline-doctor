# MASTER PROMPT — GitLab CI Auto-Fix Agent
# Paste this entire prompt into VS Code Claude Sonnet 4.6 to start building

---

## YOUR ROLE

You are a senior Python engineer and DevOps architect. You are building a
production-grade GitLab CI/CD Auto-Fix Agent from scratch. This agent detects
pipeline failures, classifies the error, fixes the code automatically using the
OpenAI API (GPT-4o), validates the fix, and pushes it back to GitLab — all
without human intervention.

You will build this project step by step, one file at a time. Do NOT skip steps.
Do NOT write placeholder code. Every function must be fully implemented and work.

---

## ⚠️ CRITICAL RULES — READ BEFORE YOU WRITE A SINGLE LINE

1. NEVER write `pass`, `TODO`, `placeholder`, or fake implementations.
2. NEVER assume environment variables exist — always check and raise clear errors.
3. NEVER push directly to main/master — always create a branch: `auto-fix/job-{id}-{timestamp}`.
4. NEVER push a fix without validating it first (lint + syntax check).
5. NEVER loop infinitely — max 3 fix attempts per pipeline, then escalate.
6. ALWAYS print to terminal when manual action is needed — prefix with `[MANUAL ACTION REQUIRED]`.
7. ALWAYS write a `.env.example` file so the user knows exactly what credentials are needed.
8. ALWAYS handle API errors, network timeouts, and GitLab rate limits gracefully.
9. Use Python 3.10+. Use `httpx` for HTTP (not `requests`). Use `python-dotenv` for env vars.
10. Every file must have a module-level docstring explaining what it does.

---

## WHAT YOU ARE BUILDING

### Project Name: `gitlab-ci-agent`

An autonomous agent that:
- Polls GitLab API every 30 seconds for failed pipelines
- Fetches and parses job logs to extract structured error info
- Classifies errors into: dependency / syntax / test / config / unknown
- Fixes each error type with the appropriate strategy
- Validates the fix before committing
- Creates a git branch, commits the fix, opens a Merge Request
- Re-triggers the pipeline on the fix branch
- Retries up to 3 times, then escalates with full context
- Stores every fix attempt in a local SQLite database (memory system)
- Checks memory BEFORE calling the AI API (learn from past fixes)
- Sends a structured fix report as terminal output and saves as JSON

---

## TECH STACK

| Purpose              | Library              |
|----------------------|----------------------|
| HTTP calls           | httpx                |
| Env variables        | python-dotenv        |
| Git operations       | gitpython            |
| AI fix engine        | openai (GPT-4o)      |
| Database / memory    | sqlite3 (built-in)   |
| Linting Python       | pylint               |
| YAML validation      | pyyaml               |
| Logging              | loguru               |
| CLI interface        | typer                |
| Scheduling           | schedule             |

---

## EXACT FILE STRUCTURE TO CREATE

```
gitlab-ci-agent/
├── .env.example              ← credentials template (create this first)
├── .gitignore
├── requirements.txt
├── README.md
├── main.py                   ← entry point, CLI with typer
├── config.py                 ← loads and validates all env vars
├── agent/
│   ├── __init__.py
│   ├── watcher.py            ← polls GitLab for failed pipelines
│   ├── log_fetcher.py        ← fetches and cleans job logs
│   ├── classifier.py         ← classifies error type + extracts context
│   ├── fix_engine.py         ← orchestrates which fixer to call
│   ├── fixers/
│   │   ├── __init__.py
│   │   ├── dependency.py     ← fixes missing packages (no AI needed)
│   │   ├── syntax.py         ← fixes syntax errors via OpenAI API
│   │   ├── test_fixer.py     ← fixes failing tests via OpenAI API
│   │   └── config_fixer.py   ← fixes .gitlab-ci.yml / env issues
│   ├── validator.py          ← validates fix before pushing
│   ├── git_manager.py        ← handles branching, commit, push, MR
│   ├── pipeline_trigger.py   ← re-triggers pipeline via GitLab API
│   ├── memory.py             ← SQLite fix history database
│   ├── reporter.py           ← generates fix report
│   └── escalator.py          ← handles failures after max retries
├── prompts/
│   └── fix_prompts.py        ← all OpenAI prompt templates (structured)
└── tests/
    ├── test_classifier.py
    └── test_memory.py
```

---

## BUILD ORDER — FOLLOW THIS EXACTLY, ONE FILE AT A TIME

### PHASE 1 — Foundation (build these first, nothing works without them)

**Step 1: `.env.example`**
Create this file with ALL required variables:
```
GITLAB_URL=https://gitlab.com
GITLAB_TOKEN=your_gitlab_personal_access_token
GITLAB_PROJECT_ID=your_project_id
GITLAB_DEFAULT_BRANCH=main
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o
MAX_FIX_ATTEMPTS=3
POLL_INTERVAL_SECONDS=30
DRY_RUN=false
```
Print to terminal:
```
[MANUAL ACTION REQUIRED] Copy .env.example to .env and fill in your credentials:
  - GITLAB_TOKEN: Go to GitLab → Settings → Access Tokens → create with 'api' scope
  - GITLAB_PROJECT_ID: Found on your GitLab project main page under the project name
  - OPENAI_API_KEY: Get from https://platform.openai.com/api-keys
  - OPENAI_MODEL: Use 'gpt-4o' (recommended) or 'gpt-4-turbo'
```

**Step 2: `requirements.txt`**
Pin exact versions:
```
httpx==0.27.0
python-dotenv==1.0.1
gitpython==3.1.43
openai==1.35.0
pylint==3.2.3
pyyaml==6.0.1
loguru==0.7.2
typer==0.12.3
schedule==1.2.2
```

**Step 3: `config.py`**
- Load all env vars using `python-dotenv`
- Validate every required variable exists — if any is missing, print:
  `[MANUAL ACTION REQUIRED] Missing env var: {VAR_NAME} — add it to your .env file`
  then raise `SystemExit(1)` with a clear message
- Return a frozen dataclass `Config` with typed fields
- Required vars: GITLAB_URL, GITLAB_TOKEN, GITLAB_PROJECT_ID, GITLAB_DEFAULT_BRANCH, OPENAI_API_KEY, OPENAI_MODEL
- Validate GITLAB_URL is a valid URL
- Validate MAX_FIX_ATTEMPTS is between 1 and 10

**Step 4: `agent/memory.py`**
- Create SQLite database `fix_history.db` on first run
- Table schema:
  ```sql
  CREATE TABLE fix_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    error_file TEXT,
    fix_applied TEXT NOT NULL,
    fix_strategy TEXT NOT NULL,
    pipeline_passed INTEGER DEFAULT 0,
    attempt_number INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  )
  ```
- Functions:
  - `save_fix(...)` → insert a fix record
  - `get_past_fix(error_type, error_message)` → check if we've seen this before
  - `update_result(pipeline_id, passed: bool)` → update after pipeline runs
  - `get_stats()` → return dict: total fixes, success rate, most common errors

---

### PHASE 2 — GitLab Integration

**Step 5: `agent/watcher.py`**
- Function `get_failed_pipelines(config) -> list[dict]`
- Call: `GET /api/v4/projects/{id}/pipelines?status=failed&per_page=5`
- Handle 401 (bad token), 404 (bad project ID), 429 (rate limit — wait 60s)
- Return list of: `{id, status, ref, sha, created_at, web_url}`
- Track already-processed pipeline IDs in memory (don't process same one twice)
- Print: `[WATCHER] Found {n} failed pipeline(s)`

**Step 6: `agent/log_fetcher.py`**
- Function `get_failed_job_logs(config, pipeline_id) -> dict`
- Step 1: GET `/api/v4/projects/{id}/pipelines/{pipeline_id}/jobs`
- Step 2: Filter for jobs where `status == "failed"`
- Step 3: GET `/api/v4/projects/{id}/jobs/{job_id}/trace` for each failed job
- Clean logs: remove ANSI color codes, remove timestamps, remove empty lines
- Return: `{job_id, job_name, stage, raw_logs, cleaned_logs, failure_reason}`
- If logs are over 8000 characters, keep first 3000 + last 3000 (most relevant)
- Print: `[LOG FETCHER] Fetched {len} chars of logs from job {job_id}`

**Step 7: `agent/classifier.py`**
- Function `classify_error(cleaned_logs: str, job_info: dict) -> dict`
- Return structured dict:
  ```python
  {
    "error_type": "dependency|syntax|test|config|unknown",
    "confidence": 0.0-1.0,
    "error_message": "exact error line",
    "error_file": "path/to/file.py or None",
    "error_line": 42 or None,
    "package_name": "numpy or None",  # for dependency errors
    "language": "python|node|go|java|unknown",
    "stage": "install|build|test|deploy",
    "raw_indicators": ["list of matched keywords"]
  }
  ```
- Classification rules (check in this order):
  1. `ModuleNotFoundError`, `No module named`, `Cannot find module`, `ImportError` → dependency
  2. `SyntaxError`, `IndentationError`, `ParseError`, `unexpected token` → syntax
  3. `AssertionError`, `FAILED`, `assert`, `Expected`, `test_` → test
  4. `yaml.scanner`, `Invalid configuration`, `.gitlab-ci.yml` → config
  5. Anything else → unknown with confidence 0.3
- Language detection: check file extensions in log paths (.py/.js/.go/.java)
- Print: `[CLASSIFIER] Error type: {type} (confidence: {confidence})`

---

### PHASE 3 — Fix Engine

**Step 8: `prompts/fix_prompts.py`**
This file contains ALL OpenAI prompt templates as system + user message pairs.
Use clear structured sections for best GPT-4o results.

```python
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
```

**Step 9: `agent/fixers/dependency.py`**
- Function `fix_dependency(error_info: dict, repo_path: str) -> dict`
- NO Claude API call needed here
- Detect manifest file:
  - Python → `requirements.txt` or `pyproject.toml`
  - Node → `package.json`
  - Go → `go.mod`
- For `requirements.txt`: append `{package_name}` on new line
- For `package.json`: add to `dependencies` key using json.load/dump
- For `pyproject.toml`: add under `[project] dependencies`
- If manifest not found, print: `[MANUAL ACTION REQUIRED] No manifest file found. Please create requirements.txt in {repo_path} and re-run the agent.`
- Verify the package exists on PyPI before adding (GET `https://pypi.org/pypi/{package}/json`)
  - If 404: print `[WARNING] Package '{package}' not found on PyPI — adding anyway, verify manually`
- Return: `{fix_applied, file_modified, strategy: "manifest_append"}`

**Step 10: `agent/fixers/syntax.py`**
- Function `fix_syntax(error_info: dict, repo_path: str, config) -> dict`
- Uses OpenAI API
- Read the broken file from disk: `open(os.path.join(repo_path, error_file)).read()`
- If file not found: print `[MANUAL ACTION REQUIRED] Cannot find file {error_file} in repo — check the path in the logs`
- Call OpenAI like this:
  ```python
  from openai import OpenAI
  from prompts.fix_prompts import SYNTAX_FIX_SYSTEM, SYNTAX_FIX_USER

  client = OpenAI(api_key=config.openai_api_key)

  response = client.chat.completions.create(
      model=config.openai_model,   # gpt-4o
      max_tokens=4096,
      temperature=0,               # always 0 for deterministic code fixes
      messages=[
          {"role": "system", "content": SYNTAX_FIX_SYSTEM},
          {"role": "user", "content": SYNTAX_FIX_USER.format(
              language=error_info["language"],
              error_message=error_info["error_message"],
              error_file=error_info["error_file"],
              error_line=error_info["error_line"],
              broken_code=broken_code
          )}
      ]
  )

  fixed_code = response.choices[0].message.content.strip()
  ```
- Validate response is not empty and does not contain markdown fences (strip them if present)
- Write fixed code back to file
- Return: `{fix_applied: "syntax_correction", file_modified, original_code, fixed_code, strategy: "openai_syntax_fix"}`

**Step 11: `agent/fixers/test_fixer.py`**
- Function `fix_test(error_info: dict, repo_path: str, config) -> dict`
- Uses OpenAI API (same pattern as syntax.py — use `TEST_FIX_SYSTEM` + `TEST_FIX_USER`)
- Extract test file path from logs (look for lines matching `test_*.py` or `*_test.py`)
- If no test file found: print `[MANUAL ACTION REQUIRED] Could not find test file in logs — check {repo_path}/tests/ manually`
- Use `temperature=0` for deterministic output
- Return: `{fix_applied, file_modified, strategy: "openai_test_fix"}`

**Step 12: `agent/fixers/config_fixer.py`**
- Function `fix_config(error_info: dict, repo_path: str, config) -> dict`
- Uses OpenAI API (same pattern — use `CONFIG_FIX_SYSTEM` + `CONFIG_FIX_USER`)
- Read `.gitlab-ci.yml` from repo root
- If missing: print `[MANUAL ACTION REQUIRED] .gitlab-ci.yml not found in {repo_path}`
- Use `temperature=0`
- After getting fixed YAML from OpenAI, validate it with `yaml.safe_load()` — if it throws, do NOT write the file, print: `[WARNING] OpenAI returned invalid YAML — skipping config fix, escalating to human`
- Return: `{fix_applied, file_modified, strategy: "openai_config_fix"}`

**Step 13: `agent/validator.py`**
- Function `validate_fix(file_path: str, language: str) -> dict`
- For Python: run `python -m py_compile {file_path}` via subprocess
  - If non-zero exit: fix is invalid, return `{valid: False, reason: stderr}`
- For YAML: run `yaml.safe_load(open(file_path))`
  - If exception: return `{valid: False, reason: str(e)}`
- For JS: run `node --check {file_path}` if node is available
  - If node not found: print `[MANUAL ACTION REQUIRED] Node.js not installed — cannot validate JS fix. Install from https://nodejs.org` — return `{valid: True, reason: "skipped - node not found"}`
- Return: `{valid: True/False, reason: str, validator_used: str}`

**Step 14: `agent/fix_engine.py`**
- Function `run_fix(pipeline_id, job_info, error_info, config, memory, repo_path) -> dict`
- Step 1: Check memory FIRST
  ```python
  past_fix = memory.get_past_fix(error_info["error_type"], error_info["error_message"])
  if past_fix:
      print(f"[MEMORY HIT] Found past fix for this error — applying without API call")
      # apply the same fix directly
  ```
- Step 2: If no memory hit, call appropriate fixer based on error_type
- Step 3: Call `validator.validate_fix()` on the modified file
  - If invalid: do NOT commit, print `[FIX INVALID] Validation failed: {reason}` and return failure
- Step 4: Save to memory with `memory.save_fix(...)`
- Step 5: Return full fix result dict
- If error_type is "unknown": print `[MANUAL ACTION REQUIRED] Unknown error type — agent cannot fix this automatically. Review logs at: {job_web_url}` and return failure without attempting fix

---

### PHASE 4 — Git Operations

**Step 15: `agent/git_manager.py`**
- Clone or use existing local repo
- On init: check if `.git` directory exists in `repo_path` — if not, clone using GitLab URL + token embedded in URL: `https://oauth2:{token}@gitlab.com/{project_path}.git`
- Print: `[MANUAL ACTION REQUIRED] Ensure the repo is cloned at {repo_path} or set REPO_PATH in .env`
- Function `create_fix_branch(job_id: str) -> str`:
  - Branch name: `auto-fix/job-{job_id}-{timestamp}`
  - Fetch latest from remote first
  - Create and checkout branch from default branch
- Function `commit_fix(file_modified: str, error_type: str, package_name: str = None) -> str`:
  - Smart commit message format:
    ```
    fix(auto): resolve {error_type} error in {file_modified}
    
    - Error type: {error_type}
    - File: {file_modified}
    - Fixed by: GitLab CI Auto-Fix Agent
    - Job ID: {job_id}
    ```
  - Stage only the modified file (not everything)
- Function `push_branch(branch_name: str)`:
  - Push to remote
  - Handle `GitCommandError` — if push fails print `[MANUAL ACTION REQUIRED] Git push failed. Check that your GitLab token has 'write_repository' permission`
- Function `open_merge_request(config, branch_name, fix_result, error_info) -> str`:
  - POST `/api/v4/projects/{id}/merge_requests`
  - Title: `fix: auto-resolved {error_type} in pipeline #{pipeline_id}`
  - Description template:
    ```markdown
    ## Auto-Fix Report
    
    **Pipeline:** #{pipeline_id}
    **Job:** {job_name} (#{job_id})
    **Error Type:** {error_type}
    **Confidence:** {confidence}
    
    ## Root Cause
    {error_message}
    
    ## Fix Applied
    {fix_applied}
    
    **File modified:** `{file_modified}`
    
    ## Validation
    - Syntax check: ✅ Passed
    - Validator used: {validator_used}
    
    ---
    *This MR was created automatically by the GitLab CI Auto-Fix Agent*
    ```
  - target_branch: default branch
  - remove_source_branch: true
  - Return MR URL
  - Print: `[GIT] Merge Request opened: {mr_url}`

---

### PHASE 5 — Pipeline Re-trigger + Escalation

**Step 16: `agent/pipeline_trigger.py`**
- Function `retrigger_pipeline(config, branch_name) -> dict`
- POST `/api/v4/projects/{id}/pipeline` with `{"ref": branch_name}`
- Poll pipeline status every 20 seconds (max 20 polls = ~7 minutes)
- Print progress: `[PIPELINE] Status: {status} (attempt {n}/20)`
- Return `{pipeline_id, status, web_url, duration_seconds}`
- If pipeline passes: print `[SUCCESS] ✅ Pipeline passed after auto-fix!`
- If pipeline fails again: return failure for escalation logic

**Step 17: `agent/escalator.py`**
- Function `escalate(pipeline_id, job_id, all_attempts: list, error_info: dict)`
- Called when max retries exceeded or fix is invalid
- Print to terminal in a clear box:
  ```
  ╔══════════════════════════════════════════╗
  ║     [ESCALATION] HUMAN REVIEW NEEDED     ║
  ╠══════════════════════════════════════════╣
  ║ Pipeline: {pipeline_id}                  ║
  ║ Job:      {job_id}                       ║
  ║ Error:    {error_type}                   ║
  ║ Attempts: {n}/{max}                      ║
  ║ Job URL:  {web_url}                      ║
  ╚══════════════════════════════════════════╝
  ```
- Save escalation to memory with `attempt_number = -1` (escalated flag)
- Create a GitLab issue via POST `/api/v4/projects/{id}/issues`:
  - Title: `[Auto-Fix Escalation] Pipeline #{pipeline_id} could not be fixed automatically`
  - Description includes all attempt history
  - Label: `auto-fix-failed`

---

### PHASE 6 — Reporting + Entry Point

**Step 18: `agent/reporter.py`**
- Function `generate_report(pipeline_id, error_info, fix_result, pipeline_result) -> dict`
- Print structured report to terminal
- Save JSON report to `reports/fix-{pipeline_id}-{timestamp}.json`
- Report includes: error type, confidence, file fixed, strategy used, time taken, pipeline result, MR URL

**Step 19: `main.py`**
- Use `typer` to build CLI with these commands:
  ```
  python main.py run          # start polling loop
  python main.py run --dry-run  # simulate without pushing
  python main.py status       # show fix history stats from DB
  python main.py fix-once --pipeline-id 123  # run on specific pipeline
  ```
- On startup, print:
  ```
  GitLab CI Auto-Fix Agent
  ========================
  Project: {project_id}
  GitLab:  {gitlab_url}
  Mode:    {"DRY RUN" if dry_run else "LIVE"}
  Polling every {interval}s
  Press Ctrl+C to stop
  ```
- Main polling loop using `schedule`:
  ```python
  schedule.every(config.poll_interval).seconds.do(run_agent_cycle)
  while True:
      schedule.run_pending()
      time.sleep(1)
  ```

**Step 20: `README.md`**
Write complete README with:
- What this project does (2 paragraphs)
- Architecture diagram (ASCII)
- Setup instructions (exact commands)
- All environment variables explained
- How to run (exact commands)
- How the memory system works
- How escalation works
- Demo flow (step by step)

---

## AFTER BUILDING EACH FILE, DO THIS

After writing each file, run:
```bash
python -c "import ast; ast.parse(open('{filename}').read()); print('✅ Syntax OK: {filename}')"
```
If it fails, fix it before moving to the next file.

---

## THINGS THAT REQUIRE MANUAL ACTION FROM THE USER

Whenever any of these situations occur, STOP and print a clear message:

| Situation | What to print |
|-----------|--------------|
| .env not filled | `[MANUAL ACTION REQUIRED] Fill in .env file before continuing` |
| Repo not cloned | `[MANUAL ACTION REQUIRED] Clone your repo to {REPO_PATH}` |
| Token missing write permission | `[MANUAL ACTION REQUIRED] GitLab token needs write_repository scope` |
| Node.js not installed | `[MANUAL ACTION REQUIRED] Install Node.js for JS validation` |
| Package not on PyPI | `[MANUAL ACTION REQUIRED] Verify package name manually` |
| Unknown error type | `[MANUAL ACTION REQUIRED] Review logs manually at {url}` |

---

## START BUILDING NOW

Begin with Step 1 (`.env.example`). After each file is complete, tell me:
- What file you just built
- What it does in one line
- What the next file is

Do not move to the next step until the current file is complete and syntactically valid.

Ask me before making any assumption about:
- The GitLab project structure
- The programming language of the target repo
- The branch protection rules
- Whether to auto-merge or only open MR

Begin now.
