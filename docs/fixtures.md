# Test Fixtures

## 1. Policy

- Fixtures are synthetic. They are built from the verified structure in [architecture.md](architecture.md) §3.4.
- No content derived from real logs, session files, or app-server responses is stored in the repository.
- Fixtures are used by automated tests only. The Collector never reads them at runtime.

## 2. Content

| Element | Rule |
|---|---|
| Key names, record types, enum values | Exactly as verified for the provider version |
| Record order and state transitions | As observed (e.g. `status: waiting` with `waitingFor`, then `idle` on decision) |
| Text fields | Fixed placeholders, e.g. `<text>` |
| Identifiers | Generated UUIDs, small integers for pid |
| Paths | `/home/user/repo/...` |
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

## 5. Layout

````text
tests/fixtures/<provider>/<version>/<scenario-id>/
├── meta.yaml        # provider, version, scenario, expected states
├── sessions/        # Claude: <pid>.json snapshots in order
├── agents/          # Claude: claude agents --json snapshots
├── appserver/       # Codex: responses and notifications, JSONL
├── logs/            # transcripts, rollouts, subagent files
├── state/           # Codex: sqlite rows as JSON
└── process.jsonl    # process view snapshots
````

`meta.yaml` lists the expected Employee assignment and activity state sequence, which tests assert against.
