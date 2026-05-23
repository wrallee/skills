---
name: headless-cli-bridge
description: >-
  Use this skill when building or adapting a Telegram/API bridge that lets a
  user drive an LLM CLI headlessly. It covers CLI discovery, auto-approve
  execution, Telegram approval gates, session handling, subprocess safety, and
  local verification.
---

# Headless CLI Bridge

Goal: build a bridge, usually a Telegram bot, that accepts user messages,
executes an LLM CLI in a fixed workspace, and returns the CLI result without
requiring an interactive terminal.

For Telegram bridges, the practical default is headless auto-approve execution
inside a constrained bridge. Do not depend on the CLI's native interactive
permission prompts unless explicitly implementing a PTY-based advanced mode.

## Required Safety Model

Use three layers:

1. Telegram/user allowlist: only configured user IDs can run the bridge.
2. Bridge-level approval gate: classify risky requests before invoking the CLI.
3. CLI execution sandbox: fixed cwd, timeout, closed stdin, bounded output, and
   a known allowlist of CLI flags.

Auto-approve flags such as `-y`, `--yolo`, or
`--dangerously-skip-permissions` are acceptable for this use case only after
the bridge has applied its own policy. They are not a substitute for user
allowlists, cwd limits, and risky-action approval.

## 1. CLI Discovery

Before writing bridge code, inspect the target CLI:

```bash
<cli_name> --help
```

Record only flags that are present in help or official docs:

- headless prompt flag, for example `--print`, `--prompt`, or `-p`
- auto-approve/headless permission flag, if any
- resume/session flag, if any
- cwd/workdir flag, if any
- output format flags, if any

Do not add model-switching, formatting, or session flags unless discovery proves
they exist. Unknown flags should fail validation before the bot is run.

## 2. Bridge Approval Gate

Prefer bridge-level approval over trying to forward the CLI's native terminal
prompt. Classify each Telegram request before invoking the CLI.

Usually auto-approve:

- reading files in the configured workspace
- searching, listing, summarizing, explaining code
- running non-mutating checks or tests that are already part of the project
- editing ordinary workspace files when the user explicitly requested it

Require Telegram approval before invoking the CLI:

- destructive commands such as `rm`, `git reset`, mass deletion, overwrite
- package installation or dependency downloads
- network access, deploys, publishing, external API calls
- `sudo`, credential changes, chmod/chown, service management
- git push, release, merge, or other irreversible remote changes
- edits outside the configured workspace

Implement approval with Telegram inline buttons or a short-lived approval token:

- store pending request ID, original text, requester ID, cwd, timestamp
- approve only if the same authorized user responds before expiry
- include a compact risk summary in the approval message
- on approval, run the CLI once with the approved request
- on denial or timeout, do not invoke the CLI

## 3. Interactive Prompt Handling

Default mode: do not try to answer native CLI prompts. Run the CLI with the
documented headless prompt flag and auto-approve flag after the bridge gate.

Advanced mode, only if requested: use a PTY to detect native CLI prompts and
relay them to Telegram. Treat this as fragile because prompt text, ANSI output,
single-key input, and TUI behavior vary by CLI version. If using PTY mode:

- pattern-match prompts narrowly
- show the prompt to the same authorized user
- wait with a strict timeout
- write the user's response back to the PTY
- log raw PTY output to a local debug file with secrets redacted
- fall back to terminating the subprocess if the prompt cannot be parsed

## 4. State And Storage Discovery

Use native CLI session/resume flags first. Avoid editing internal history files.

If session discovery is needed:

- inspect only the target CLI's documented or obvious app data directory
- open a small real transcript sample and identify the JSON/schema shape
- redact tokens, secrets, and private message text from logs
- never truncate, delete, or rewrite CLI-owned history unless the user
  explicitly asked for a repair/migration and a backup has been made

For Telegram bridges, maintain bridge-owned state separately:

- authorized user IDs
- default workspace/cwd
- active session ID per user/workspace, if supported by the CLI
- pending approval requests
- per-user concurrency lock or queue

## 5. Subprocess Execution Pattern

Use a non-interactive subprocess by default:

```python
res = subprocess.run(
    cmd,
    cwd=workspace,
    input=None,
    stdin=subprocess.DEVNULL,
    capture_output=True,
    text=True,
    timeout=300,
    check=False,
)
```

Implementation requirements:

- build `cmd` as a list, never a shell string
- validate CLI path and flags against discovery results
- set a fixed workspace cwd; reject paths outside it unless approved
- use `stdin=subprocess.DEVNULL` so hidden prompts fail instead of hanging
- set a timeout and report timeout clearly
- keep raw stdout/stderr in debug logs, but redact secrets
- sanitize only the user-facing message; do not discard raw diagnostics
- bound Telegram message length and send long output as chunks or files
- serialize concurrent requests per user/session unless the CLI is proven safe

For typing indicators, run a background loop and stop it in `finally`:

```python
stop_typing = threading.Event()
try:
    typing_thread = threading.Thread(target=typing_loop, daemon=True)
    typing_thread.start()
    res = subprocess.run(..., timeout=300, stdin=subprocess.DEVNULL)
finally:
    stop_typing.set()
```

## 6. Output Cleanup

Separate raw diagnostics from user display:

- raw debug log: stdout, stderr, command list, return code, duration
- user message: cleaned CLI answer plus concise error summary if needed

Only remove known harmless boilerplate from the user message, such as fixed
warnings discovered during local tests. Do not use broad regexes that can hide
real errors.

When showing session history, strip wrapper tags such as
`<USER_REQUEST>...</USER_REQUEST>` only for display. Preserve raw stored data.
Include timestamps and workspace labels in `/resume` lists.

## 7. Local Verification

Before handing the bridge over, run a local headless smoke test:

```bash
python3 -c 'import subprocess; res=subprocess.run(["<cli_path>", "<auto_approve_flag>", "<headless_flag>", "hello"], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, check=False); print("rc=", res.returncode); print("stdout=", res.stdout[:500]); print("stderr=", res.stderr[:500])'
```

Verify:

- command exits without waiting for stdin
- return code and stderr behavior are understood
- stdout contains the expected answer
- timeout path works
- risky request path creates a Telegram approval request instead of invoking
  the CLI immediately
- denied or expired approval does not invoke the CLI

## Completion Report

When finishing a bridge task, report:

- discovered CLI flags used
- safety policy and approval-gated actions
- session/resume behavior
- local smoke test command and result
- known limitations, especially whether PTY prompt relay is unsupported
