# Test Fixtures

## 1. Policy

- Fixtures are synthetic. They are built from the verified structure in [architecture.md](architecture.md) Section 3.4.
- No content derived from real logs, session files, or app-server responses is stored in the repository.
- Fixtures are used by automated tests only. The Collector never reads them at runtime.
- Fixtures are produced by a generator per provider (`tests/fixtures/<provider>/generate.py`). Edit the generator, not the generated files.
- Fixtures include record types and keys the Adapter ignores, so that tolerance is tested.

## 2. Content

| Element | Rule |
|---|---|
| Key names, record types, enum values | Exactly as verified for the provider version |
| Record order and state transitions | As observed (e.g. `status: waiting` with `waitingFor`, then `idle` on decision) |
| Text fields | Fixed placeholders, e.g. `<text>` |
| Identifiers | Generated UUIDs, small integers for pid |
| Paths | `/home/user/repo/...`; `/home/user/notes` for a directory outside any repository |
| Timestamps | Fixed base time with relative offsets |

## 3. Validation Against Real Structure

A fixture set is validated on a Host with real sessions, read-only:

- Compare key sets per record type, enum values, and record order between the fixture and real files of the same provider version.
- Report differences only. No real content leaves the Host.

Validation is repeated when a provider version changes.

## 4. Scenarios

| ID | Provider | Scenario | Target |
|---|---|---|---|
| S01 | both | One turn that reads a file and runs a shell command | Turn, tool, thinking |
| S02 | both | A command that hits an `ask` rule; deny once, approve once | Waiting |
| S03 | both | A failing command | Tool failure stays `working` |
| S04 | both | Subagent launch | Contractor |
| S05 | claude | Agent launches `codex` from its shell | Child-process Contractor |
| S06 | both | Resume and fork | Resume, fork |
| S07 | claude | `/clear` within one process | New session in one process |
| S08 | both | Model and effort change | Condition |
| S09 | codex | Same task under two Codex homes | Account |
| S10 | both | Two concurrent agents in one repository, one in tmux, one without | Seat assignment |
| S11 | both | Agent outside any repository | Common Office |
| S12 | both | Usage limit reached | `limited` |
| S13 | both | Agent-level error | `error` |
| S14 | both | Normal exit | Off duty |

Generated: Claude S01, S02, S03, S04, S06, S07, S08, S10, S11, S13, S14; Codex S01, S02, S03, S04, S06, S08, S09, S10, S11, S12, S13, S14. Claude S12 awaits verification of its live usage-limit source; S05 awaits child-process Contractor support.


Notes on what the generated scenarios can show:

- Codex S03: the failure is only in the tool output text, which is not read; the Employee stays `working` either way.
- Codex S10: app-server shifts carry no runtime location, so a thread in tmux cannot be told apart; seats follow the session and the lowest free seat.
- S11: outside a repository, Claude records omit `gitBranch`; Codex `gitInfo` and `session_meta.git` are null.
- S13: the Claude error record (`isApiErrorMessage`, `apiError`, `apiErrorStatus`) and Codex `task_complete.error` value are placeholders; the Adapters read only their presence.

## 5. Layout

````text
tests/fixtures/<provider>/<version>/<scenario-id>/
├── meta.yaml        # provider, version, scenario, expectations
├── timeline.jsonl   # ordered operations replayed by the test harness
├── sessions/        # Claude: <pid>.json snapshots in order
├── agents/          # Claude: claude agents --json snapshots
├── appserver/       # Codex: responses and notifications, JSONL
├── logs/            # transcripts, rollouts, subagent files
├── state/           # Codex: sqlite rows as JSON
└── process.jsonl    # process view snapshots
````

`timeline.jsonl` operations:

| `op` | Effect |
|---|---|
| `session_write` | Copies a `sessions/` snapshot to `<home>/sessions/<pid>.json` |
| `session_remove` | Removes `<home>/sessions/<pid>.json` (process exit) |
| `log_append` | Appends a line range of a `logs/` file to the transcript path for `cwd` and `session`, or to `path` relative to the home |
| `file_write` | Claude: copies a `logs/` file to `path` relative to the home (subagent `.meta.json`) |
| `appserver_thread` | Codex: a thread already loaded when the Collector first connects |
| `appserver_notify` | Codex: applies a notification (`thread/started`, `thread/status/changed`, `thread/closed`) to the fake daemon and delivers it |
| `appserver_disconnect` | Codex: breaks the current app-server connection |

For Codex, `log_append` uses `path` relative to the Codex home. An operation with `home: <n>` applies to Codex home `n` (default 1); the harness runs one daemon and Adapter per home, with account alias `codex-account-<n>`. Thread `path` values under `/home/user/.codex` (home 1) or `/home/user/.codex-<n>` are rewritten to that test home.

The harness resolves `/home/user/repo` and its subdirectories to the Project `github.com/example/repo` and any other directory to the Common Office, and maps conditions with the default rules of a new Branch configuration.

The harness polls the Adapters after each operation and feeds the Judge. `meta.yaml` `expect` entries name the step (`after`) and the expected `seat`, `project`, `presence`, `state`, `tool`, `workload`, `reset_at`, `session_id`, runtime `location`, `account_alias`, `model`, `effort`, `condition`, hired `contractors` (state and tool), or state history of the selected Employee, and the number of Employees (`agent_count`) and of ended Contractors (`contractors_ended`). The Employee is selected by `pid` (Claude), else by `seat` (default 1) within `project` when given. `ref` and `same_as` assert Employee identity across steps; `shift_ref` and `same_shift_as` assert the same shift. Every emitted message is validated against the protocol schema and must not contain fixture placeholders for text, tool input or output, home paths, or provider tool ids.
