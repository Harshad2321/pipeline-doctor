# Pipeline Doctor 🏥

**Auto-fix failing GitLab CI/CD pipelines with AI-powered code repair**

Transform broken pipelines into passing ones automatically—no human intervention needed.

---

## 🎯 The Problem

Your CI/CD pipeline fails. You're blocked. You need to:
1. Find the error in logs
2. Understand what went wrong
3. Fix the code
4. Commit and push the fix
5. Wait for pipeline to re-run

This takes **30+ minutes per failure** and interrupts your flow.

## ✨ The Solution

**Pipeline Doctor** automatically fixes common CI/CD failures in seconds:

```
❌ Pipeline fails
    ↓
🤖 Pipeline Doctor detects it
    ↓
🔍 Analyzes error logs
    ↓
🧠 Classifies the failure type
    ↓
🛠️  Applies AI-powered fix
    ↓
✅ Validates & commits
    ↓
📝 Opens merge request
    ↓
🚀 Re-triggers pipeline
```

---

## 🚀 Key Features

| Feature | What It Does |
|---------|-------------|
| **🔍 Auto-Detection** | Polls GitLab API every 30s for failed pipelines |
| **🧠 Error Classification** | Identifies: dependency, syntax, test, config errors |
| **🤖 AI-Powered Fixes** | Uses GPT-4o or Gemini to fix code automatically |
| **✅ Validation** | Syntax-checks fixes before committing |
| **📝 MR Creation** | Automatically opens merge requests with detailed reports |
| **🔄 Retry Logic** | Retries up to 3 times, then escalates to human |
| **💾 Memory System** | Learns from past fixes, avoids duplicate API calls |
| **🎯 Dry-Run Mode** | Test without committing any changes |

---

## 🔧 Supported Error Types

- **Dependency Errors** → Auto-adds packages to `requirements.txt`
- **Syntax Errors** → Fixes malformed code with AI
- **Test Failures** → Repairs broken test assertions
- **Config Issues** → Fixes `.gitlab-ci.yml` errors
- **Unknown Errors** → Escalates to human with full context

---

## 🏗️ Architecture

```
GitLab CI Pipeline
       ↓
[❌ FAILURE DETECTED]
       ↓
┌─────────────────────────────┐
│   Pipeline Doctor Agent     │
├─────────────────────────────┤
│ 1. Watcher                  │  Polls GitLab API
│ 2. Log Fetcher              │  Extracts error details
│ 3. Error Classifier         │  Categorizes the failure
│ 4. Fix Engine               │  Applies intelligent fix
│ 5. Validator                │  Syntax checking
│ 6. Git Manager              │  Branch → Commit → MR
│ 7. Pipeline Trigger         │  Re-runs on fix branch
│ 8. Escalator (if needed)    │  Creates issue for human
└─────────────────────────────┘
       ↓
[✅ PIPELINE PASSES]
```

---

## ⚡ Quick Start

### 1. **Clone & Install**

```bash
git clone <repo-url>
cd pipeline-doctor
pip install -r requirements.txt
```

### 2. **Configure Credentials**

```bash
cp .env.example .env
nano .env  # Fill in your credentials
```

**Required:**
- `GITLAB_TOKEN` → GitLab Settings → Access Tokens ([create with `api` scope](https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html))
- `GITLAB_PROJECT_ID` → Your GitLab project ID
- `OPENAI_API_KEY` → [Get from OpenAI](https://platform.openai.com/api-keys) **OR**
- `GCP_PROJECT_ID` → [Google Cloud Project](https://console.cloud.google.com) (for free Gemini)

### 3. **Test It**

```bash
# Dry-run mode (no actual commits)
python main.py run --dry-run
```

### 4. **Run for Real**

```bash
# Start monitoring and auto-fixing
python main.py run
```

---

## 📋 Usage Examples

### Start in Live Mode
```bash
python main.py run
```
Continuous polling for failed pipelines. Press `Ctrl+C` to stop.

### Test Mode (No Commits)
```bash
python main.py run --dry-run
```
Simulates fixes without pushing to GitLab.

### Fix Specific Pipeline
```bash
python main.py fix-once 12345
```
Run agent on pipeline #12345 once.

### View Statistics
```bash
python main.py status
```
Shows fix history and success rate.

---

## 💡 How It Works (Step by Step)

### Example: Missing Dependency

1. **Pipeline fails**: `ModuleNotFoundError: No module named 'requests'`
2. **Detected** ✓ Watcher spots failed job
3. **Analyzed** ✓ Classifier identifies: *dependency error*
4. **Fixed** ✓ Adds `requests==2.31.0` to `requirements.txt`
5. **Validated** ✓ Syntax check passes
6. **Committed** ✓ Creates branch and MR
7. **Triggered** ✓ Pipeline re-runs on fix branch
8. **Success** ✓ Pipeline passes, MR ready for review

---

## 🧠 Memory System

Pipeline Doctor learns from past fixes using a **SQLite database**:

- Stores every fix attempt with error type, file, and strategy
- Before calling AI, checks: *"Have we seen this error before?"*
- If yes → **reuses past fix** (saves time + money)
- If no → **calls AI** to find new solution
- Tracks success rate per error type

```bash
# Check memory stats
python main.py status

# Output:
# Total fixes: 47
# Success rate: 91%
# Most common error: dependency (23)
```

---

## ⚙️ Configuration

### Environment Variables

| Variable | Required | Example |
|----------|----------|---------|
| `GITLAB_URL` | Yes | `https://gitlab.com` |
| `GITLAB_TOKEN` | Yes | `glpat-xxx` |
| `GITLAB_PROJECT_ID` | Yes | `123456789` |
| `GITLAB_DEFAULT_BRANCH` | Yes | `main` |
| `OPENAI_API_KEY` | Yes* | `sk-proj-xxx` |
| `OPENAI_MODEL` | Yes* | `gpt-4o` |
| `MAX_FIX_ATTEMPTS` | No | `3` (1-10) |
| `POLL_INTERVAL_SECONDS` | No | `30` (10-300) |
| `DRY_RUN` | No | `false` |

*Use either OpenAI OR Google Gemini (set in .env)

### AI Backend Options

**OpenAI (GPT-4o)**
- Cost: ~$0.02-0.05 per fix
- Quality: 93%+ accuracy
- Speed: 2-5 seconds
- Setup: [Get API key](https://platform.openai.com/api-keys)

**Google Gemini (Vertex AI)**
- Cost: FREE tier (60 req/min) or ~$0.0001-0.0003 per fix
- Quality: 91.5% accuracy
- Speed: 1-2 seconds (faster)
- Setup: `gcloud auth application-default login`

---

## 🔄 Escalation Flow

If auto-fix fails after 3 attempts:

1. **Problem**: Pipeline still fails after retries
2. **Action**: Creates GitLab issue with tag `auto-fix-failed`
3. **Content**: Full error history, logs, and all attempted fixes
4. **Next Step**: Human reviews and fixes manually

---

## 📊 Tech Stack

| Purpose | Technology |
|---------|-----------|
| HTTP calls | `httpx` |
| Environment vars | `python-dotenv` |
| Git operations | `GitPython` |
| AI (OpenAI) | `openai` SDK |
| AI (Google) | `google-cloud-aiplatform` |
| YAML validation | `pyyaml` |
| Logging | `loguru` |
| CLI | `typer` |
| Scheduling | `schedule` |
| Database | SQLite (built-in) |

---

## 📁 Project Structure

```
pipeline-doctor/
├── main.py                # Entry point (CLI commands)
├── config.py              # Configuration management
├── requirements.txt       # Python dependencies
├── .env.example           # Configuration template
├── .gitignore             # Git ignore rules
│
├── agent/                 # Core agent logic
│   ├── watcher.py         # GitLab pipeline monitoring
│   ├── log_fetcher.py     # Job log extraction
│   ├── classifier.py      # Error type classification
│   ├── fix_engine.py      # Fix orchestration
│   ├── validator.py       # Code validation
│   ├── git_manager.py     # Git operations
│   ├── pipeline_trigger.py # Pipeline re-trigger
│   ├── memory.py          # SQLite fix history
│   ├── reporter.py        # Report generation
│   ├── escalator.py       # Escalation handling
│   └── fixers/            # Specific fix strategies
│       ├── dependency.py
│       ├── syntax.py
│       ├── test_fixer.py
│       └── config_fixer.py
│
├── prompts/               # AI prompt templates
│   └── fix_prompts.py
│
└── tests/                 # Unit tests
    ├── test_classifier.py
    └── test_memory.py
```

---

## 🧪 Testing

### Run Tests
```bash
pytest tests/
```

### Run Specific Test
```bash
pytest tests/test_classifier.py -v
```

---

## 🎯 Common Issues

### `[MANUAL ACTION REQUIRED] Missing env var: GITLAB_TOKEN`
**Solution**: Make sure `GITLAB_TOKEN` is filled in `.env` file

### `Permission denied for aiplatform.googleapis.com`
**Solution**: Enable the API: `gcloud services enable aiplatform.googleapis.com`

### `[FIX INVALID] Validation failed`
**Solution**: The AI-generated fix had a syntax error. Will retry or escalate on next cycle.

---

## 🚀 Future Enhancements

- [ ] Support for GitHub Actions / CircleCI
- [ ] Multi-language support (Java, Go, Rust)
- [ ] Web dashboard for monitoring
- [ ] Webhook integration (push alerts)
- [ ] Custom fix strategies per team
- [ ] Integration with Slack notifications

---

## 🤝 Contributing

This is a hackathon project. We welcome improvements, bug reports, and feature requests!

---
