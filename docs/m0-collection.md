# M0 Sample Collection and Anonymization

## 1. Scope

Samples establish how each provider exposes the observations listed in [architecture.md](architecture.md) §3.2. Log locations and formats are verified on the Host; nothing below is assumed correct until confirmed.

## 2. Environment Record

Record once per Host, per provider version:

````bash
claude --version
codex --version
uname -sr
````

## 3. Log Location

Candidate locations, to be confirmed:

| Provider | Candidate |
|---|---|
| Claude Code | `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl` |
| Codex | `~/.codex/sessions/YYYY/MM/DD/*.jsonl` |

Confirm by listing files modified during a scenario:

````bash
touch /tmp/m0-mark
# run the scenario
find ~/.claude ~/.codex -type f -newer /tmp/m0-mark 2>/dev/null
````

Every file reported is collected, including files outside the candidate paths.

## 4. Process and Runtime Record

Captured while the scenario is running. Command-line arguments are excluded.

````bash
ps -eo pid,ppid,lstart,comm | grep -Ei 'claude|codex|node'
for p in $(pgrep -f 'claude|codex'); do echo "$p $(readlink /proc/$p/cwd)"; done
tmux list-panes -a -F '#{session_name} #{pane_id} #{pane_pid} #{pane_current_path}'
````

## 5. Scenarios

Each scenario runs in a scratch repository with a Git remote, unless stated otherwise.

| ID | Provider | Scenario | Target observation |
|---|---|---|---|
| S01 | both | One prompt that reads a file and runs a shell command | `turn.*`, `tool.*`, `generation.*` |
| S02 | both | A command that requires approval; approve after 30 s | `input.requested` |
| S03 | both | A command that fails (e.g. failing test) | `tool.finished` with failure |
| S04 | claude | Task that launches a subagent | `subagent.*` |
| S05 | claude | Agent launches `codex` from its shell | Child-process Contractor |
| S06 | both | Exit, then resume the same session | `session.started` with resume |
| S07 | claude | `/clear` within one process | New session in same process |
| S08 | both | Change model and effort mid-session | `model.changed` |
| S09 | codex | Switch account, then resume | `account.changed` |
| S10 | both | Two concurrent agents in the same repository, one in tmux, one without tmux | Seat assignment |
| S11 | both | Agent started outside any repository | Common Office |
| S12 | both | Usage limit reached (collect when it occurs) | `limit.*` |
| S13 | both | Agent-level error, e.g. network disconnected during a turn | `agent.error` |
| S14 | both | Normal exit | `process.exited` |

## 6. Anonymization

### 6.1 Preserve

- JSON structure, key names, value types, line order.
- Event and record type fields.
- Timestamps. A constant offset may be applied to all timestamps in one sample.
- Tool names, model names, runtime settings (effort, fast mode).
- Error types and codes, usage-limit reset times, token counts.
- Identifier consistency: the same original value maps to the same replacement across all files of a sample.
- Identifier format: a UUID is replaced by a UUID, a path by a path.

### 6.2 Replace

| Content | Replacement |
|---|---|
| Prompt and response text | `<text:N>` where N is the original length |
| Tool input and output content | `<tool-input:N>`, `<tool-output:N>` |
| File paths | `/home/user/repo/...` with relative structure kept |
| User, host, and organization names | `user`, `host`, `org` |
| Email addresses and account identifiers | `user@example.com`, `account-1`, `account-2` |
| Git remote URLs | `github.com/example/repo` |
| Session, request, and message identifiers | Consistent generated UUIDs |
| Tokens, keys, cookies, authorization headers | `<secret>` |

### 6.3 Verify

A sample is accepted only when the following search returns nothing:

````bash
grep -rEi "$USER|$(hostname)|@[a-z0-9.-]+\.[a-z]{2,}|/home/[^u]|sk-|ghp_|github_pat_|xox[bp]-|Bearer " <sample-dir>
````

## 7. Sample Layout

````text
tests/fixtures/<provider>/<version>/<scenario-id>/
├── meta.yaml        # provider, version, scenario, timestamp offset
├── logs/            # anonymized log files, original relative names
├── process.txt      # anonymized §4 output
└── tmux.txt         # anonymized §4 output, if applicable
````
