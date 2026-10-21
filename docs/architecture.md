# AgentVille Architecture

## 1. Domain Model

### 1.1 Visual and Execution Terms

| Visual term | Execution concept |
|---|---|
| HQ | The Host running the central hub. HQ is a role; it is also a regular Host. |
| Branch | A Host. |
| Project | One repository. |
| Common Office | The Project for agents started outside any repository. |
| Employee | An `Agent`: a persistent agent identity within a Project on a Host. |
| Contractor | An `AgentInstance` with a `parent_instance_id` (subagent). |
| Condition | Display mapping of an Employee's model and runtime settings. |

Visual terms are presentation only. The data model uses execution concepts.

### 1.2 Host

Each Host defines only itself in a user-level configuration file outside the repository (`~/.config/agentville/`). The file is created on first start.

| Field | Description |
|---|---|
| `id` | Unique, immutable identifier. |
| `alias` | Display name. Mutable. |
| `country` | Real or fictional. |
| `time` | Real time zone (e.g. `Asia/Seoul`) or fictional label. |
| `location` | Real or fictional. |
| `hq.url` | HQ endpoint. The only remote information a Host holds. |

- All internal references use `id`. `alias` is display only.
- Event timestamps (`event_at`, `observed_at`) are always UTC.
- A real time zone in `time` drives local day/night rendering. A fictional value is rendered as a label only.

### 1.3 Project

- One repository is one Project, regardless of Host.
- Employees of the same Project on different Hosts are shown in the same room as remote collaboration.
- Agents started outside any repository belong to the Common Office.

#### Identification

| Case | Rule |
|---|---|
| Repository with a Git remote | Identified automatically by the normalized remote URL (scheme, user, and `.git` suffix removed). |
| Repository without a remote | Local Project of that Branch, identified by `(host, path)`. |
| Fork or mirror | Grouped manually in Branch configuration. |

- `alias` for a Project is set in Branch configuration. Default is the repository name.

### 1.3.1 Room

- One Room per Project. The mapping is always one-to-one.
- The Common Office is the Room for agents outside any repository.

### 1.4 Employee

An Employee is an `Agent` in the data model. Each shift is an `AgentInstance` linked to its `Agent`.

An `Agent` is identified by:

```text
(project, host, provider, seat)
```

- `seat` is a number distinguishing concurrent agents of the same provider in the same Project on the same Host.
- One shift of an Employee is defined per provider by its Adapter (see 3.4). For Claude Code, one process lifetime; for Codex, one loaded-thread lifetime on the app-server.
- Account and model are Employee attributes. Changes are recorded as history.

#### Seat assignment

When a new agent process is observed, the Employee is selected in this order:

1. The Employee who last worked on the resumed session (including resume under a different account).
2. The Employee matching the previous runtime location (e.g. tmux pane).
3. The Employee with the lowest free seat number.

A candidate already on shift is skipped and the next rule applies.

#### Employee states

| Observation | State |
|---|---|
| Process running | On duty |
| Process exited, less than threshold | Off duty |
| Process exited, threshold or longer | On leave |

- Threshold default: 7 days. Configurable per Branch.
- A new process for an existing Employee returns that Employee to on duty.

### 1.5 Contractor

- A subagent is an `AgentInstance` with `parent_instance_id`.
- In-process subagent: identified by `(parent_instance_id, provider_subagent_id)`.
- Child-process agent (e.g. another agent CLI launched from the parent's shell): identified by process; parent resolved from the process tree.
- A Contractor's lifetime does not exceed its parent's.

### 1.6 Condition

- Derived from model and runtime settings (e.g. effort level, fast mode).
- The mapping table is a configuration file with defaults, editable per Branch.
- Unmapped combinations use the `normal` condition.

```yaml
conditions:
  - provider: claude
    model: "claude-opus-*"
    effort: high
    condition: study-mode
  - provider: claude
    fast_mode: true
    condition: extra-coffee
  - provider: codex
    effort: low
    condition: lazy
```

### 1.7 Handover Between Providers

- When work moves to a different provider in the same Project by separate invocation, no handover relationship is recorded.
- The Project timeline shows the events in time order.

### 1.8 Branch and Project Lifecycle

| Event | Result |
|---|---|
| Host heartbeat lost | Branch unreachable. Employee states are retained and marked unverifiable. |
| Host heartbeat restored | Branch reachable. Observation resumes. |
| Owner closes a Branch or Project at HQ | HQ record is closed. No command is sent to any Branch. |
| Agent observed in a closed Branch or Project | Automatically reopened. HQ raises a notification. |

## 2. State Model

### 2.1 Layers

| Layer | Entity | States |
|---|---|---|
| Presence | `Agent` | on duty, off duty, on leave |
| Activity | `AgentInstance` (on duty only) | `working`, `thinking`, `waiting`, `idle`, `completed`, `error`, `limited`, `unknown` |

- Activity states exist only while on duty.
- When a Branch is unreachable, presence and activity keep their last observed values and are marked unverifiable.

### 2.2 Activity States

| State | Evidence | Location | Rendering |
|---|---|---|---|
| `working` | Tool execution started, not finished. Tool failures (tests, compile errors) remain `working`. | Desk | Hands moving, head turning |
| `thinking` | Explicit model-generation signal. Not inferred when the provider emits none. | Desk | Thought bubble; posture chosen randomly per occurrence (chin on hand or leaning back) |
| `waiting` | Explicit user-input or approval request. | Desk | Waving hand. No time-based transition. HQ notification. |
| `idle` | Alive, no active turn. | See 2.3 | See 2.3 |
| `completed` | Provider turn-completed event. | Desk | Momentary checkmark, then `idle` |
| `error` | Agent-level failure (API error, authentication failure, abnormal halt). Normal process exit is not an error. | Infirmary | HQ notification |
| `limited` | Provider usage-limit event. | Desk | Computer off, watching wall clock. Reset time shown on the clock when available. No time-based transition. No HQ notification. |
| `unknown` | Insufficient or contradictory evidence. | Desk | Dimmed, question mark overhead |

### 2.3 Idle Progression

| Idle duration | Location | Rendering |
|---|---|---|
| 0 to 5 min | Desk | Looking at screen, hands still |
| 5 to 30 min | Desk | Looking at phone |
| 30 to 60 min | Desk | Dozing |
| 60 min or longer | Lounge | Fika |

- Thresholds are defaults, configurable per Branch.
- On any new work, the Employee returns to the desk immediately.

### 2.4 Shared Facilities

| Facility | Scope | Used by |
|---|---|---|
| Lounge | One per Branch | `idle` 60 min or longer |
| Infirmary | One per Branch | `error` |

- Co-location in a facility is presentation only. It is never recorded as collaboration.
- An Employee in the infirmary returns to the desk on resumed normal activity, or goes off duty from the infirmary on process exit.

### 2.5 Workload

- The number of monitors on an Employee's desk scales with tool execution count in a recent time window.
- Window size and count-to-monitor mapping are defaults, configurable per Branch.

## 3. Collector

The Collector runs on each Branch as a systemd user service under the owning user's account. Root is never required.

### 3.1 Components

| Component | Responsibility | Provider-specific |
|---|---|---|
| Adapter | Discovers provider processes and logs; converts them into observations. | Yes |
| Judge | Determines Employee assignment, activity state, and condition from observations. | No |
| Store | Persists raw observations, Employee history, and `seq` (SQLite). | No |
| Sender | Delivers messages to HQ per [protocol.md](protocol.md). | No |

### 3.2 Observations

An Adapter emits only the observations its provider exposes.

| Observation | Content | Used for |
|---|---|---|
| `process.started` | pid, start time, working directory, parent pid, runtime location | On duty, Project, seat assignment |
| `process.exited` | pid | Off duty |
| `session.started` | session id | Seat assignment |
| `session.status` | normalized live status: `active`, `idle`, `waiting`, `unknown` | Activity state |
| `turn.started` | | `working` or `thinking` |
| `generation.started` / `generation.ended` | | `thinking` |
| `tool.started` / `tool.finished` | tool name, success | `working`, workload |
| `input.requested` / `input.resolved` | reason | `waiting` |
| `turn.completed` | | `completed`, then `idle` |
| `limit.reached` / `limit.cleared` | reset time, if known | `limited` |
| `agent.error` | | `error` |
| `model.changed` | model, runtime settings | Condition |
| `account.changed` | account identity (Branch-local only) | Account attribute |
| `subagent.started` / `subagent.ended` | subagent id, provider | Contractor |

Every observation carries observed time, event time, source (`session_file`, `session_log`, `app_server`, `hook`, `process`), and raw location (log file and offset) when read from a log.

### 3.3 Reading

- Logs are read incrementally from the last position (inode, offset), triggered by file change notification.
- A transcript with no stored position is read from its end when attached; history before attach is not replayed. A transcript created after attach is read from its start.
- At attach, model and effort are taken from the last non-error assistant record in the transcript tail.
- A session file that exists but cannot be parsed keeps the current shift; a shift ends only when its file is gone or its process is not alive.
- Liveness: `/proc/<pid>/stat` exists, the process is not a zombie, and field 22 (start time in clock ticks) equals `procStart`.
- Rotation, truncation, and partial trailing lines are handled.
- Secrets matching token and key patterns are redacted before persistence.
- Retention of raw observations is configurable per Branch.
- Basic observation never modifies agent configuration. Hooks are optional enhancements.

### 3.4 Provider Sources

Verified on Claude Code 2.1.303 and Codex CLI 0.163.0 (app-server 0.162.1 / 0.163.0).

#### Claude Code

| Purpose | Source |
|---|---|
| Live sessions, shift | `~/.claude/sessions/<pid>.json` (`pid`, `procStart`, `sessionId`, `status`, `statusUpdatedAt`, `cwd`, `tmux`, `kind`). Equivalent view: `claude agents --json`. |
| Shift identity | `(pid, procStart)` |
| Detail | `~/.claude/projects/<encoded-cwd>/<sessionId>.jsonl` |
| Turn completed | `system` record, `subtype: turn_duration`; `assistant` `stop_reason: end_turn` |
| Thinking | `assistant` content item `thinking`; `thinkingDurationMs` |
| Tool | `tool_use` (`id`, `name`) → `tool_result` (`tool_use_id`, `is_error`) |
| Waiting | `sessions/<pid>.json` `status: waiting` with `waitingFor` present; cleared on decision. Not recorded in transcripts while open (trailing `tool_use` without `tool_result`). Outcome afterwards: `permissionDecision` (accept) or `toolDenialKind` (deny). |
| Session status values | File: `idle`, `busy`, `shell`, `waiting`. `claude agents --json`: `status` as above or `null`; `state`: `working`, `blocked`, `null`. |
| Usage limit | `quotaLimits` (`status`, `rateLimitType`, `resetsAt`) |
| Error | `isApiErrorMessage`, `apiError`, `apiErrorStatus` |
| Model, effort | `requestedModel`, `effort`, `perTurnEffort`; `attachment` `type: model` |
| Resume | `--resume` and `--continue` keep the same `sessionId` and append to the same file. |
| Fork | `--fork-session` creates a new `sessionId` with no reference to the origin. |
| Continuation | `continued-in` record in the old file (`continuedInSessionId`) |
| Contractor | `tool_use` `name: Agent` → `toolUseResult.agentId`; `<sessionId>/subagents/agent-<agentId>.jsonl` and `.meta.json` (`toolUseId`); subagent records carry the parent `sessionId` |
| Project | `cwd`, `gitBranch` on records |

#### Codex

| Purpose | Source |
|---|---|
| Live threads, shift | App-server daemon per Codex home (`<launcher> app-server daemon version` → `socketPath`); JSON-RPC over WebSocket on the control socket: `thread/loaded/list`, `thread/read`, `thread/list` |
| Shift identity | Thread `id` while its status is not `notLoaded` |
| State changes | Notification `thread/status/changed` (`threadId`, `status`). Delivered to a passive client that only lists and reads; no subscription required. Turn and item notifications are not delivered to such a client. |
| Thread status | `notLoaded`, `idle`, `systemError`, `active` with `activeFlags`: `waitingOnApproval`, `waitingOnUserInput` |
| Turn | `turn/started`, `turn/completed` |
| Tool | `item/started`, `item/completed` |
| Detail | `<codex-home>/sessions/YYYY/MM/DD/rollout-<timestamp>-<uuid>.jsonl` |
| Usage limit | rollout `event_msg` `token_count.rate_limits` (`primary.resets_at`) |
| Error | status `systemError`; rollout `task_complete.error` |
| Model, effort | rollout `thread_settings_applied`, `turn_context` |
| Resume | Same session id; appends to the same rollout file. |
| Fork, Contractor | Thread `forkedFromId`, `parentThreadId`; `state_5.sqlite` `thread_spawn_edges` |
| Project | Thread `cwd`, `gitInfo` |
| Account | Codex home (one daemon per home) |

- No pid is exposed by Codex logs, sqlite state, or app-server responses.
- The Collector acts as a read-only app-server client. Only `thread/loaded/list` and `thread/read` are called; no method that starts, resumes, sends to, or interrupts a thread.
- Only loaded threads are read. Reading a `notLoaded` thread is avoided until its side effects are verified.
- `thread/loaded/list` and `thread/read` seed state on connect and after reconnect; afterwards state follows `thread/status/changed`. `optOutNotificationMethods` is never set for it.
- Turn and tool detail come from the thread's rollout file, not from app-server notifications.
- Threads that are not Employees: `parentThreadId` set or `source.subAgent` (future Contractors), and `threadSource: system` (internal threads, typically with a null `path`).
- Rollout path: `Thread.path`; when null, `<codex-home>/sessions/*/*/*/rollout-*-<thread-id>.jsonl`.
- Responses carry no `jsonrpc` field; the client does not require it. Server-to-client requests (approvals) are never answered.
- On loss of the app-server connection, every Codex shift is reported `unknown` until the next seed.
- Codex runs that do not use the shared daemon (e.g. IDE extension, `codex exec`) are observed from rollout files only; waiting state is unavailable for them.

#### Antigravity CLI

| Purpose | Source |
|---|---|
| Live sessions | `~/.gemini/antigravity-cli/presence/<conversation-uuid>.lock` held by a live `agy` process |
| Detail | `brain/<conversation-uuid>/.system_generated/logs/transcript.jsonl` (`type`, `source`, `status`: `DONE`, `ERROR`, `RUNNING`) |

Antigravity waiting and usage-limit signals are not yet identified.

### 3.5 Configuration

`$XDG_CONFIG_HOME/agentville/config.yaml` (default `~/.config/agentville/config.yaml`), mode 0600, created on first start. `host.id` is generated once and never rewritten.

````yaml
host:
  id: <uuid>
  alias: <hostname>
  country: ""
  time: <local time zone>
  location: ""
hq:
  url: http://127.0.0.1:8470
thresholds: {phone: 300, doze: 1800, lounge: 3600, leave: 604800}
providers:
  claude: {home: ~/.claude}
  codex:
    - {home: ~/.codex, account_alias: codex}
conditions:
  - {provider: claude, fast_mode: true, condition: extra-coffee}
  - {provider: "*", effort: high, condition: study-mode}
  - {provider: "*", effort: low, condition: lazy}
collector: {poll_interval: 1.0, heartbeat_interval: 30}
````

- Codex homes present at first start are listed automatically.
- Condition rules are evaluated in order; the first match wins; `model` accepts shell-style patterns.

### 3.6 Run Loop

- Each tick polls every Adapter, applies observations to the Judge, and emits messages.
- The first tick emits a `snapshot` instead of individual changes. A `heartbeat` is emitted every `heartbeat_interval`.
- `seq` is reserved in blocks of 1000 in `$XDG_STATE_HOME/agentville/seq` (default `~/.local/state/agentville/seq`), written with fsync before use; a restart resumes after the reserved bound.
- A failing Adapter is logged to stderr and skipped for that tick; other Adapters continue.
- Time-based presence changes (off duty to on leave) are emitted when the threshold passes, without a new event.
- Until the Sender exists, messages are written as JSONL to stdout or a file (`agentville-collector --output`).
- Service: `deploy/systemd/agentville-collector.service` (systemd user unit).

## 4. HQ

- Storage: SQLite (WAL). Current state per Branch and message history.
- History retention: configurable. Default 30 days.
- Browser API: REST for the full current state; WebSocket for changes. On reconnect, the browser fetches the full state via REST first.
- Bound to `127.0.0.1` by default. Exposure beyond loopback requires authentication.

## 5. Transport

- The Collector on the HQ Host uses the same protocol over loopback.
- Remote Branches connect outbound to HQ only. HQ never connects to a Branch.
- Transport: HTTPS POST.
- Authentication: per-Branch token, issued and revoked at HQ.

## 6. Web UI

- Navigation: Town map (Branches) → Branch building → Room. A Dashboard mode is available alongside.
- Remote Employees of the same Project appear in the same Room with a Branch `alias` badge.
- Inspector: shift history, sessions, attributes, recent state changes.
- Notifications: `waiting`, `error`, reopened Branch or Project, unreachable Branch.
- Assets: original simple pixel art. External assets only with verified licenses.

## 7. Repository Layout

````text
agentville/
├── pyproject.toml
├── schemas/protocol-v1.schema.json
├── packages/agentville/
│   ├── common/          # observations, protocol envelope
│   └── collector/       # jsonl reader, project resolver, judge, adapters/
├── tests/{unit,integration,fixtures}/
└── docs/
````

## 8. Milestones

| Milestone | Scope |
|---|---|
| M0 | Inspect real Claude and Codex logs and process mappings on Linux. Produce anonymized fixtures. |
| M1 | Collector: Adapters, Judge, Store. Branch-side state determination. |
| M2 | HQ and live Dashboard. |
| M3 | Pixel office. |
| M4 | Hardening and release. |

## 9. Open Items

- Default values: workload window, monitor mapping, process scan interval, heartbeat interval.
- Claude Code: meaning of `state: blocked` and `status: shell`.
- Codex: live observation of `waitingOnApproval`, `waitingOnUserInput`, and `systemError`.
- Antigravity waiting and usage-limit signals.
- Contractor grouping when counts are large (Codex subagent threads dominate recent history).
- English terms pending confirmation: on duty, off duty, on leave, shift, seat, unreachable, closed.
