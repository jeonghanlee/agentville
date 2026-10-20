# M0 Sample Collection and Anonymization

## 1. Scope

Samples are anonymized fixtures for Adapter development and tests. Each sample captures, for one scenario, every source listed in [architecture.md](architecture.md) §3.4 that the scenario touches.

Collection runs as the owning user, read-only against existing sessions. Test sessions run in a scratch directory.

## 2. Environment Record

Recorded once per sample set:

````bash
claude --version
codex --version
codex-personal app-server daemon version
codex-work app-server daemon version
uname -sr
````

## 3. Sources

| Provider | Source | Capture |
|---|---|---|
| Claude Code | `~/.claude/sessions/<pid>.json` | Snapshot on every change (poll at 0.5 s), with capture time |
| Claude Code | `~/.claude/projects/<encoded-cwd>/<sessionId>.jsonl` | Full file after the scenario |
| Claude Code | `~/.claude/projects/<encoded-cwd>/<sessionId>/subagents/` | All `agent-*.jsonl` and `agent-*.meta.json` |
| Claude Code | `claude agents --json` | Snapshot at each state change |
| Codex | App-server `thread/loaded/list`, `thread/read` (read-only client, poll at 1 s) | Response on every status change, with capture time |
| Codex | App-server notifications received by the read-only client | All, with receive time |
| Codex | `<codex-home>/sessions/YYYY/MM/DD/rollout-*.jsonl` | Full file after the scenario |
| Codex | `<codex-home>/state_5.sqlite` `threads`, `thread_spawn_edges` | Rows for the scenario's threads only |
| All | Process view: `comm`, pid, parent chain, `/proc/<pid>/cwd` | Snapshot at each state change. No arguments, no environment. |
| All | `tmux list-panes -a -F '#{session_name} #{pane_id} #{pane_pid} #{pane_current_path}'` | Snapshot at start |

Never captured: `~/.claude/sessions/*.key`, credentials, process arguments, environment variables.

## 4. Scenarios

| ID | Provider | Scenario | Target |
|---|---|---|---|
| S01 | both | One prompt that reads a file and runs a shell command | Turn, tool, thinking |
| S02 | both | A command that hits an `ask` rule; deny once, approve once | Waiting |
| S03 | both | A command that fails (e.g. failing test) | Tool failure stays `working` |
| S04 | both | Task that launches a subagent | Contractor |
| S05 | claude | Agent launches `codex` from its shell | Child-process Contractor |
| S06 | both | Exit, then resume; also fork | Resume, fork |
| S07 | claude | `/clear` within one process | New session in one process |
| S08 | both | Change model and effort mid-session | Condition |
| S09 | codex | Same task under the personal and work homes | Account |
| S10 | both | Two concurrent agents in one repository, one in tmux, one without tmux | Seat assignment |
| S11 | both | Agent started outside any repository | Common Office |
| S12 | both | Usage limit reached (collect when it occurs) | `limited` |
| S13 | both | Agent-level error (e.g. network disconnected during a turn) | `error` |
| S14 | both | Normal exit | Off duty |

Each scenario runs interactively (Claude Code session in tmux; Codex through the shared daemon) unless stated otherwise.

## 5. Anonymization

### 5.1 Preserve

- JSON structure, key names, value types, record order.
- Record type, subtype, status, and state values.
- Timestamps. One constant offset may be applied per sample.
- Tool names, model names, runtime settings.
- Error types and codes, rate-limit reset times, token counts.
- Identifier consistency within a sample: one original value maps to one replacement in every file.
- Identifier format: UUID to UUID, path to path, integer to integer.

### 5.2 Replace

| Content | Replacement |
|---|---|
| Prompt and response text, thinking text | `<text:N>` (N = original length) |
| Tool input and output content | `<tool-input:N>`, `<tool-output:N>` |
| `waitingFor` | First token kept, rest `<text:N>` |
| File paths and `cwd` | `/home/user/repo/...`, relative structure kept |
| Encoded project directory names | Re-encoded from the replaced `cwd` |
| User, host, and organization names | `user`, `host`, `org` |
| Email addresses, account and user identifiers | `user@example.com`, `account-1`, `account-2` |
| Git remote URLs | `github.com/example/repo` |
| Session, thread, agent, request, message identifiers | Consistent generated UUIDs |
| pid, `procStart`, `pidDomain` | Consistent small integers and placeholders |
| tmux session names and socket paths | `tmux-1`, `/tmp/socket-1` |
| Tokens, keys, cookies, authorization headers | `<secret>` |

### 5.3 Verify

A sample is accepted only when this search returns nothing:

````bash
grep -rEi "$USER|$(hostname)|@[a-z0-9.-]+\.[a-z]{2,}|/home/[^u]|sk-|ghp_|github_pat_|xox[bp]-|Bearer " <sample-dir>
````

## 6. Sample Layout

````text
tests/fixtures/<provider>/<version>/<scenario-id>/
├── meta.yaml        # provider, version, scenario, timestamp offset, capture notes
├── sessions/        # Claude: <pid>.json snapshots, one file per capture
├── agents/          # Claude: claude agents --json snapshots
├── appserver/       # Codex: responses and notifications, JSONL with capture time
├── logs/            # transcripts, rollouts, subagent files
├── state/           # Codex: selected sqlite rows as JSON
├── process.jsonl    # process view snapshots
└── tmux.txt
````
