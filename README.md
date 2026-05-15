# diffmind

AI-powered git diff reviewer. Stream a structured code review for any diff — single commits, commit ranges, staged changes, or piped diffs — with concurrent batch mode for reviewing multiple commits at once.

```
diffmind review                      # review current branch vs main (streaming Rich UI)
diffmind review --focus issues       # only flag bugs and security concerns
diffmind score                       # complexity/risk score — no AI, instant
diffmind batch abc123 def456 ghi789  # review 3 commits concurrently
diffmind log --n 10 --format json    # review last 10 commits, export as JSON
diffmind history list                # browse past reviews
git diff | diffmind review           # pipe any diff directly
```

## What's New in v1.2.0

- **Missing module fixes** — `config.py`, `scorer.py`, and `history.py` are now included in the package. All commands (`review`, `score`, `batch`, `log`, `history`) work without crashing on import.
- **HTML export** — `diffmind review --format html > report.html` generates a self-contained dark-themed single-file HTML report. No external dependencies required.

```bash
# Generate an HTML report for staged changes
diffmind review --staged --format html > staged-review.html

# Review a commit range and export to HTML
diffmind review --commits main HEAD --format html > pr-review.html

# Pipe a diff and export to HTML
git diff HEAD~1 | diffmind review --format html > last-commit.html
```

## What's New in v1.1.0

- **`diffmind score`** — Instant complexity and risk scoring with no AI required. Counts lines added/removed, categorises files (source vs test vs config vs migrations), computes a 0–100 risk score, and prints a Rich breakdown table. Great for a quick sanity check before hitting the AI.
- **Config file** — `~/.diffmind.toml` sets persistent defaults for `model`, `focus`, `format`, and `save_history`. No more repeating `--model claude-sonnet-4-6` on every invocation.
- **Review history** — Pass `--save` on any `review` call to append to `~/.diffmind/history.jsonl`. Browse with `diffmind history list`, show stats with `diffmind history stats`, and clear with `diffmind history clear`.

```bash
# Score a diff before reviewing it
diffmind score --staged

# Save reviews to history
diffmind review --staged --save

# Browse history
diffmind history list --n 20
diffmind history stats

# ~/.diffmind.toml
# model        = "claude-sonnet-4-6"
# focus        = "issues"
# save_history = true
```

**Sample score output:**

```
╭─ diffmind score  staged ──────────────────────────────╮
│  Label               staged                           │
│  Lines added         +147                             │
│  Lines removed       -23                              │
│  Net change          +124                             │
│  Total churn         170                              │
│  Files changed       8                                │
│    Source files      5                                │
│    Test files        2                                │
│    Config/infra      1                                │
│    Migrations        0                                │
│  Test coverage ratio 25%                              │
│  Risk level          MEDIUM  32/100                   │
╰───────────────────────────────────────────────────────╯
Notes:
  • Moderate churn: 170 lines changed
  • Touches config/infra files: pyproject.toml
```

## Breakthrough techniques

- **LLM integration** — Streams structured reviews via the Anthropic API (`claude-haiku-4-5-20251001` by default for speed; swap to `claude-sonnet-4-6` for deeper analysis). Each review is a real-time stream — text appears as the model generates it.
- **Full async architecture** — `batch` and `log` commands use `asyncio.TaskGroup` (Python 3.11 structured concurrency) to fetch and review multiple diffs concurrently with bounded `asyncio.Semaphore` control.
- **Live Rich UI** — The `review` command renders markdown analysis inside a `Rich.Live` panel that updates in real-time as tokens stream in from the API.

## Install

```bash
pip install diffmind
export ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

### `diffmind review` — single diff, streaming

```bash
# Review changes on current branch vs main
diffmind review

# Review vs a different base branch
diffmind review --base develop

# Review staged changes
diffmind review --staged

# Review unstaged working-tree changes
diffmind review --working

# Review a specific commit
diffmind review --commits abc1234

# Review a commit range (base HEAD)
diffmind review --commits main HEAD

# Pipe any diff
git diff HEAD~3 | diffmind review
curl https://patch-url | diffmind review

# Choose focus
diffmind review --focus summary    # brief 3-5 sentence summary
diffmind review --focus issues     # only bugs / security
diffmind review --focus suggest    # improvement suggestions only
diffmind review --focus full       # full structured review (default)

# Choose model (haiku=fast, sonnet=deep)
diffmind review --model claude-sonnet-4-6

# Output formats
diffmind review --format rich      # live streaming Rich panel (default)
diffmind review --format markdown  # plain markdown to stdout
diffmind review --format json      # machine-readable JSON
```

**Sample output (rich):**

```
╭─ ✓ Done  main..HEAD  3 files: src/auth.py, tests/test_auth.py, README.md ─╮
│                                                                             │
│  ## Summary                                                                 │
│  This diff adds JWT-based authentication to the REST API, replacing the    │
│  previous session-cookie approach. The change affects the login endpoint,  │
│  a new token refresh route, and accompanying tests.                        │
│                                                                             │
│  ## Key Changes                                                             │
│  - `AuthService.login()` now returns a signed JWT instead of setting a     │
│    session cookie                                                           │
│  - New `/auth/refresh` endpoint added with a 15-minute access token TTL   │
│  - Test coverage expanded from 3 to 11 cases                               │
│                                                                             │
│  ## Potential Issues                                                        │
│  - Token secret is read from `os.environ` without a fallback; will raise   │
│    `KeyError` if `JWT_SECRET` is missing in production                     │
│                                                                             │
│  ## Verdict                                                                 │
│  Needs work                                                                 │
╰─────────────────────────────────────────────────────────────────────────────╯
```

### `diffmind batch` — multiple commits, concurrent

Reviews N commits simultaneously using `asyncio.TaskGroup`. Results stream in as each review finishes (not in commit order — whichever finishes first prints first).

```bash
# Review 3 commits concurrently
diffmind batch abc123 def456 ghi789

# Tune concurrency (default: 4)
diffmind batch abc123 def456 --concurrency 2

# Export all reviews as JSON
diffmind batch abc123 def456 --format json > reviews.json

# Export as a single Markdown document
diffmind batch abc123 def456 --format markdown > reviews.md
```

**Sample output (batch, json):**

```json
[
  {
    "label": "abc123ab: fix: handle None in user lookup",
    "model": "claude-haiku-4-5-20251001",
    "ok": true,
    "truncated": false,
    "files_changed": ["src/users.py"],
    "error": "",
    "review": "## Summary\nThis commit fixes a NullPointerError ..."
  }
]
```

### `diffmind log` — review recent commits

```bash
# Review last 5 commits (default)
diffmind log

# Review last 20
diffmind log --n 20

# Deep analysis with sonnet
diffmind log --n 5 --model claude-sonnet-4-6 --focus full

# Export for CI/reporting
diffmind log --n 10 --format markdown > weekly-review.md
```

## Architecture

```
diffmind/
├── differ.py     # async git subprocess wrappers (diff_commits, diff_commit, …)
├── reviewer.py   # streaming review via Anthropic SDK; batch_review uses TaskGroup
├── scorer.py     # diff complexity/risk scoring (no AI)
├── formatter.py  # rich / markdown / json output renderers
├── history.py    # append-only JSONL review history log
├── config.py     # ~/.diffmind.toml config loader
└── cli.py        # argparse CLI wiring all commands together
```

- **`differ.py`** — All git interactions are `async def` functions using `asyncio.create_subprocess_exec`. Multiple diffs are fetched concurrently in `batch` and `log` via `TaskGroup`.
- **`reviewer.py`** — `stream_review()` is synchronous (wraps the Anthropic streaming context manager); `stream_review_async()` runs it in an executor so it can be awaited from async code. `batch_review()` uses `asyncio.TaskGroup` with a `Semaphore` to cap concurrency.
- **`formatter.py`** — Stateless functions: `format_rich`, `format_markdown`, `format_json`.

## Options reference

| Flag | Default | Description |
|------|---------|-------------|
| `--model` | `claude-haiku-4-5-20251001` | Claude model ID |
| `--focus` | `full` | `full` / `summary` / `issues` / `suggest` |
| `--format` / `-f` | `rich` | `rich` / `markdown` / `json` |
| `--base` | `main` | Base branch for `review` |
| `--save` | off | Append review to `~/.diffmind/history.jsonl` |
| `--concurrency` / `-c` | `4` | Max concurrent reviews in `batch` / `log` |
| `--cwd` | current dir | Git repository path |

## Requirements

- Python ≥ 3.11 (uses `asyncio.TaskGroup`)
- `anthropic >= 0.20`
- `rich >= 13.0`
- `git` on `$PATH`
- `ANTHROPIC_API_KEY` environment variable

## License

MIT
