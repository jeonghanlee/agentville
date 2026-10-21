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
| Store | Persists the Employee roster and the reserved `seq` bound in the state directory. | No |
| Sender | Delivers messages to HQ per [protocol.md](protocol.md). | No |

Store files in `$XDG_STATE_HOME/agentville/` (default `~/.local/state/agentville/`), mode 0600, replaced atomically with fsync:

| File | Content |
|---|---|
| `seq` | Reserved upper bound of `seq` |
| `roster.json` | Per Employee: `agent_id`, `project_id`, `project_alias`, `provider`, `seat`, `presence_since`, on-duty flag, runtime location, last 20 session ids, `account_alias`, model, settings |

- The roster is saved when an Employee is emitted or a session id is recorded. It holds no activity, paths, prompts, or tool data.
- At start, Employees are restored off duty. One that was on duty at the last save is off duty from the start time. Running processes then return to their Employees by the seat rules.
- An unreadable roster starts empty.

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
| `subagent.started` / `subagent.status` / `subagent.ended` | subagent id, provider, normalized status (`active`, `waiting`, `idle`, `error`, `unknown`), tool name | Contractor |

Every observation carries observed time, event time, source (`session_file`, `session_log`, `app_server`, `hook`, `process`), and raw location (log file and offset) when read from a log.

- Subagent observations carry the parent's shift. A Contractor's id is derived from the parent instance id and the provider subagent id; neither the provider id nor prompts, task descriptions, subagent types, or tool arguments are sent.
- Contractors are held in memory only, included in snapshots while hired, and ended with their parent shift.
- `limited` persists through `turn.completed` and `idle` status. It clears on `limit.cleared` (to `idle`), `turn.started`, `tool.started`, or `active` status. `reset_at` is sent while `limited`.
- Child-process Contractors (§1.5) are not yet implemented.

### 3.3 Reading

- Logs are read incrementally from the last position (inode, offset) on every tick.
- A transcript with no stored position is read from its end when attached; history before attach is not replayed. A transcript created after attach is read from its start; a resumed one (Claude: first record older than attach; Codex: thread `createdAt` older than attach; either: already followed earlier in the run) is read from its end.
- Attaching in the middle of a line resumes at the next line. A line that is not valid UTF-8 JSON is skipped.
- A transcript or rollout that cannot be read is reported and skipped for that poll without affecting other shifts. A JSON-RPC error on one Codex `thread/read` skips that thread for the poll; transport errors reconnect.
- At attach, model and effort are taken from the last non-error assistant record in the transcript tail.
- A session file that exists but cannot be parsed keeps the current shift; a shift ends only when its file is gone or its process is not alive.
- Liveness: `/proc/<pid>/stat` exists, the process is not a zombie, and field 22 (start time in clock ticks) equals `procStart`.
- Rotation, truncation, and partial trailing lines are handled.
- Raw observations are not persisted.
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
| Account | Claude home (one configuration directory per account) |

- Contractor: an `Agent` `tool_use` hires one, keyed by its `id`; the matching `tool_result` ends it. The subagent transcript is the `agent-*.jsonl` whose `.meta.json` `toolUseId` matches; it is read from its start. Its `tool_use` sets the tool, `tool_result` clears it, and `stop_reason: end_turn` or `turn_duration` sets `idle`. Without that file the Contractor is `working` with no tool. A session change ends open Contractors.
- Usage limit and thinking are not yet read.

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
| Usage limit | rollout `event_msg` `token_count.rate_limits`: `primary`, `secondary` (`used_percent`, `window_minutes`, `resets_at` in epoch seconds) |
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
- Threads that are not Employees: subagent threads (`parentThreadId` set or `source.subAgent`), and `threadSource: system` (internal threads, typically with a null `path`, ignored).
- A loaded subagent thread is a Contractor of the shift of its `parentThreadId` (for a nested subagent, the root shift); one whose parent is not a shift is not tracked. State follows its thread status (`active` → `working`, `waitingOn*` → `waiting`, `idle`, `systemError` → `error`); the tool comes from its rollout. It ends when the thread is closed, `notLoaded`, absent at a seed, or when the parent shift ends.
- A `token_count` with any window at `used_percent` ≥ 100 reports `limit.reached` with the latest `resets_at` of those windows; a later one with every window below 100 reports `limit.cleared`.
- Rollout path: `Thread.path`; when null, `<codex-home>/sessions/*/*/*/rollout-*-<thread-id>.jsonl`.
- Responses carry no `jsonrpc` field; the client does not require it. Server-to-client requests (approvals) are never answered.
- On loss of the app-server connection, every Codex shift and Contractor is reported `unknown` until the next seed.
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
  claude:
    - {home: ~/.claude, account_alias: claude-account-1}
  codex:
    - {home: ~/.codex, account_alias: codex-account-1}
    - {home: ~/.codex-2, account_alias: codex-account-2}
conditions:
  - {provider: claude, fast_mode: true, condition: extra-coffee}
  - {provider: "*", effort: high, condition: study-mode}
  - {provider: "*", effort: low, condition: lazy}
collector: {poll_interval: 1.0, heartbeat_interval: 30}
````

- One provider home is one account. At first start, `~/.<provider>` and existing `~/.<provider>-*` directories are listed in that order as `<provider>-account-1`, `<provider>-account-2`, …; `~/.claude` is always listed. Account names and homes are local settings.
- A single mapping (`claude: {home: ~/.claude}`) is read as a one-account list.
- Values are validated at start: `heartbeat_interval` ≥ 1, thresholds ≥ 0 with `phone` ≤ `doze` ≤ `lounge`. A file holding `hq.token` must not be accessible by group or others.
- A loopback HQ is contacted without environment proxies.
- Condition rules are evaluated in order; the first match wins; `model` accepts shell-style patterns.

### 3.6 Run Loop

- A tick runs every `collector.poll_interval` seconds (default 1.0). Each tick polls every Adapter, applies observations to the Judge, and emits messages.
- The first tick emits a `snapshot` instead of individual changes. A `heartbeat` is emitted every `heartbeat_interval`.
- `seq` is reserved in blocks of 1000 in `$XDG_STATE_HOME/agentville/seq` (default `~/.local/state/agentville/seq`), written with fsync before use; a restart resumes after the reserved bound.
- A failing Adapter is logged to stderr and skipped for that tick; other Adapters continue.
- Time-based presence changes (off duty to on leave) are emitted when the threshold passes, without a new event.
- Services: `deploy/systemd/agentville-collector.service` and `deploy/systemd/agentville-hq.service` (systemd user units).

## 4. HQ

- Process: `agentville-hq` (FastAPI, uvicorn), bound to `127.0.0.1:8470` by default.
- Storage: SQLite (WAL) at `$XDG_DATA_HOME/agentville/hq.sqlite3` (default `~/.local/share/agentville/hq.sqlite3`).

| Table | Content |
|---|---|
| `messages` | Every accepted message, keyed by `(branch_id, seq)` |
| `branches` | Branch payload, last `seq`, last seen time, heartbeat interval |
| `agents`, `activities`, `contractors` | Current state, keyed by `(branch_id, id)` |

- Message history retention: 30 days by default (`--retention-days`); current state is never pruned.

### 4.1 Ingest Rules

Messages of one batch are applied in `seq` order:

| Case | Result |
|---|---|
| `(branch_id, seq)` already stored with the same `sent_at` | Duplicate; ignored |
| `snapshot` | Replaces all current state of the Branch. A snapshot whose `seq` is not above the last applied `seq` (Branch lost its sequence state) also discards stored messages from that `seq` on and restarts the numbering. |
| `snapshot` with `seq` not above the last applied and `sent_at` earlier than the latest applied `sent_at` | Stale, not applied; response asks for a snapshot |
| `seq` lower than the last applied | Stale; stored, not applied |
| `seq` not equal to last + 1, or no state for the Branch | Applied; response asks for a snapshot |
| `agent` with no instance | Employee updated; its activity removed |
| `contractor` with status `ended` | Contractor removed |

The latest applied `sent_at` is not advanced by a value more than 5 minutes ahead of HQ's clock.

A Branch is reported unreachable when no message arrived within three heartbeat intervals (30 s assumed before its first heartbeat).

### 4.2 API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness |
| `POST` | `/api/v1/ingest/messages` | Branch ingest, body `{"messages": [...]}`, one Branch per batch, at most 1000 messages |
| `GET` | `/api/v1/state` | Branches (with `reachable`), agents, activities, contractors |
| `GET` | `/api/v1/branches` | Branches |
| `GET` | `/api/v1/agents` | Agents |
| `GET` | `/api/v1/stats` | Ingest totals since HQ start |

Ingest response: `{"accepted", "duplicates", "stale", "need_snapshot"}`.

### 4.3 Authorization

- A Branch connecting from loopback needs no token, unless `--no-trust-loopback` is set (required behind a local reverse proxy).
- Any other Branch needs a bearer token listed for its `branch_id` in the HQ token file (`--tokens`, YAML mapping of `branch_id` to token, mode 0600, each token a string of at least 16 characters). The Branch sets the same value as `hq.token` in its configuration.
- A caller that is neither trusted loopback nor holding any configured token is rejected before the body is read.
- Binding to a non-loopback address requires `--allow-remote` and `--viewer-token-file`; read endpoints then require the viewer token, and loopback Branches need tokens too.
- Messages are schema-validated after authorization, including `date-time` formats. Non-finite numbers (`NaN`, `Infinity`) and excessive nesting are rejected. Request bodies are limited to 4 MiB, counted while reading.
- Ingest accepts only `Content-Type: application/json` and rejects requests carrying an `Origin` header, so a web page cannot submit messages through the trusted loopback path.
- On a loopback bind, requests whose `Host` is not `127.0.0.1`, `::1`, `localhost`, the bind address, or a `--server-name` value are rejected (DNS rebinding guard).
- `--server-name` names the public host of a reverse proxy and requires `--no-trust-loopback` and `--viewer-token-file`.
- `WS /ws/v1/live` accepts a browser only when its `Origin` matches the request `Host` or names a `--server-name`. Rejected sockets are closed with code 4403 (origin or host) or 4401 (viewer token).
- Ingest responds after storing. Each viewer has its own sender holding only the latest state, with a 5 s send limit; a viewer that exceeds it is disconnected without delaying others.
- The Collector refuses to send a token over plain HTTP to a non-loopback HQ and does not follow redirects.
- On shutdown HQ checkpoints the WAL and closes the database.

## 5. Transport

- The Collector sends each tick's messages as one batch by HTTP(S) POST to `hq.url`. Remote Branches connect outbound only; HQ never connects to a Branch.
- On delivery failure the batch is dropped and the next successful delivery starts with a snapshot. Retries back off from 1 s to 60 s.
- When HQ reports `need_snapshot`, the next tick sends a snapshot.
- `agentville-collector --output <path|->` writes JSONL instead of sending, for diagnostics.

## 6. Web UI

- Navigation: Virtual office, Dashboard, Employees, Projects, Timeline, Branches, and display settings.
- Remote Employees of the same Project appear in the same Room with a Branch `alias` badge.
- Employee detail: current activity, condition, tool name, workload, Project, Branch alias, usage-limit reset time when known, and the Employee's Contractors with provider badge, activity, and tool name.
- Status filters and Branch indicators highlight waiting Employees, errors, and unverified connections.
- Visual style: Cyworld-inspired isometric minirooms with chibi pixel characters, as inspiration only; original artwork, no copied graphics or brand assets.

### 6.1 Workspace and live data

- Served by HQ at `/` (static HTML, CSS, JavaScript, and bundled artwork; no build step). The initial view is the virtual office.
- Live data: `WS /ws/v1/live` sends `{"type": "state", "state": ...}` (the `/api/v1/state` shape) on connect, after ingest (bursts coalesced), and every 10 s. The page reconnects with backoff up to 30 s.
- With a viewer token, the page reads it from the URL fragment (`#token=...`), keeps it in session storage, removes it from the address bar, and passes it as the `token` query parameter of the socket.
- Close code 4401 shows that a viewer token is required and 4403 that HQ refused the connection; neither is retried.
- Idle detail (at desk, phone, dozing, fika) is computed in the page from `state_since` and the Branch thresholds.
- Branch-provided text is rendered as text only, never as markup.

### 6.2 Virtual office presentation

- The floor combines `office.png` with textured Employee and cat atlases rendered by `art.js` and `sprites.js`. Artwork generation inputs and asset paths are recorded in `design/office-artwork.prompt.txt` and `design/character-artwork.prompt.txt`.
- Twelve Employee appearances combine hair colors, glasses, hats, and headphones. The complete roster receives balanced assignments before filtering, and existing assignments remain stable during the browser visit. Each appearance has matching standing, seated, rear-facing, and reclining sprites; `*-varied.png` atlases supply the six additional appearances, with generation inputs recorded in `design/employee-appearance.prompt.txt`.
- Each Project occupies one room. The office displays two Project rooms at a time; room navigation exposes additional Projects. Common Office, Fika, and the infirmary remain available.
- Employees from another Branch appear beside local Employees of the same Project, with a Branch alias badge. Contractors stand beside their parent with a hard hat, independently of the parent's seated, reclining, or coffee pose. Each shown Contractor takes the pose and state mark of its own activity (an absent or unrecognized state shows as `unknown`), and its label shows the provider badge, activity, and tool name while `working`. Up to two Contractors are drawn per Employee; the last one drawn carries a "+N" count of the remainder.
- Activity controls character gestures. Idle thresholds select desk, phone, dozing, or Fika presentation; errors move Employees to the infirmary. The phone action takes priority over the extra-coffee prop. A `completed` activity shows a checkmark over the character for 4 s from the first observation of that `state_since`, including after a following `idle`. Because the Collector can report `completed` and `idle` together, an Employee last observed as `working` or `thinking` that becomes `idle` shows the same checkmark; other transitions to `idle` and the first observation of an Employee do not. With reduced motion the checkmark is static. A `limited` Employee shows a wall clock; the visible screen of a rear-facing desk is darkened, and other placements show a small switched-off monitor beside the character. A known `reset_at` appears as "Resets" with a time in the character label and detail. `unknown` characters are dimmed and desaturated. The `study-mode` condition adds a book stack on the desk side of the character.
- Desk positions align seated bodies with chair cushions and working hands with keyboards and mice at every viewport and zoom level; characters scale proportionally with the artwork. Furniture and characters share a depth order. Selected Employees show an outline of body portions hidden behind furniture. The infirmary has one bed with a reclining pose. Fika has three seats. Facility seats remain reserved until the occupant leaves, including during coffee visits. Additional occupants stand in a first-arrival waiting line and take the next vacant seat or bed. The scene shows up to six standing Fika occupants and four standing infirmary occupants; further occupants remain in the count and team list, and selecting one reveals that Employee in a standing spot without changing queue order.
- Working Employees independently alternate three typing and three mouse gestures. Cheese and Pepper independently walk, sit, groom, and nap along connected floor routes; walking animates their paws and tails.
- Fika Employees occasionally walk to the coffee machine, wait for brewing, receive one of ten cup designs, and return to their seat. Visits affect presentation only and stop when the Employee leaves Fika. Only one Employee uses the machine at a time.
- Window lighting follows the displayed Branch's local time: morning from 05:00, day from 10:00, evening from 17:00, and night from 20:00. Night windows show a moon and stars while indoor lamps remain warm. When the Branch `time` is a valid IANA time zone, the heading clock, date, window lighting, and usage-limit reset times use that zone and the clock is labeled with the zone; a missing or fictional value falls back to browser-local time labeled "Your local time".
- Search, status filters, and room filters select the team list and highlight matching characters. Selecting a teammate opens their current details. Selection survives Project-page changes while the Employee still matches the filters. Remote participants of local Projects remain visible in shared facilities on every Project page.
- Dashboard and Employees provide tabular views. Workload is shown as the reported count of recent tool executions ("N recent tools"); the window size is not displayed because it is not part of the payload. Projects and Branches link to the office; Timeline shows current activity and changes observed during the browser visit.
- Display settings control name labels, reduced motion, and automatic or manually selected window light. The interface also respects the system reduced-motion preference. Hidden views and reduced motion pause random office activity.
- The browser marks activity unverified when its HQ connection is lost or the Branch is unreachable. Tables mark on-duty, off-duty, and on-leave rows of such Branches alike. Placement, pose, and counts keep the last observed state, dimmed and marked with "?".

### 6.3 Synthetic demonstration mode

The `/?demo=1` URL loads fictional teammates from `demo.js` and displays a Demo label. It does not open a live socket or write to HQ. Display settings switch between Demo and live views.

## 7. Repository Layout

````text
agentville/
├── pyproject.toml
├── packages/agentville/
│   ├── common/          # observations, protocol envelope, schemas/protocol-v1.schema.json
│   ├── collector/       # jsonl reader, project resolver, judge, adapters/, config, sender, run loop
│   └── hq/              # store, API, entry point, web/ (office and Dashboard)
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
- Switching the login within one Claude home: not yet in use; decided when adopted. Accounts in separate homes are configured per home.
- Contractor grouping when counts are large (Codex subagent threads dominate recent history).
- English terms pending confirmation: on duty, off duty, on leave, shift, seat, unreachable, closed.
