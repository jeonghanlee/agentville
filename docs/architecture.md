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
| `time` | IANA time zone (e.g. `Asia/Seoul`) or fictional label. Defaults to the host's local zone at first start. |
| `location` | Real or fictional. |
| `hq.url`, `hq.token` | HQ endpoint and, when HQ requires one, the Branch token. The only remote information a Host holds. |

- All internal references use `id`. `alias` is display only.
- Event timestamps (`event_at`, `observed_at`) are always UTC.
- A valid IANA zone in `time` drives the Branch clock, date, window light, and reset times in the Web UI. Any other value is shown as a label only, and the Web UI falls back to browser time for day/night and the clock (Section 6.2).

### 1.3 Project

- One repository is one Project, regardless of Host.
- Employees of the same Project on different Hosts are shown in the same room as remote collaboration.
- Agents started outside any repository belong to the Common Office.

#### Identification

| Case | Rule |
|---|---|
| Repository with a Git remote | Identified automatically by the normalized `origin` remote URL (scheme, user, port, and `.git` suffix removed; host lowercased). |
| Repository without a remote | Local Project of that Branch, identified by a hash of `(host, path)`. |
| Fork or mirror | Grouped manually in Branch configuration. Not implemented (Section 9). |

- The Project `alias` is the base name of the repository directory. Setting it in Branch configuration is not implemented (Section 9).

### 1.3.1 Room

- One Room per Project. The mapping is always one-to-one.
- The Common Office is the Room for agents outside any repository.

### 1.4 Employee

An Employee is an `Agent` in the data model. Each shift is an `AgentInstance` linked to its `Agent`.

An `Agent` is identified by:

```text
(project, host, provider, seat)
```

- `seat` is a number unique among the Employees of one provider on one Host, so the default display name `<Provider> <seat>` (e.g. "Codex 2") names one Employee on a Branch. Employees of different Projects never share a seat number.
- One shift of an Employee is defined per provider by its Adapter (Section 3.4). For Claude Code, one process lifetime; for Codex, one loaded-thread lifetime on the app-server, or, for a run outside the app-server daemon, the period its rollout file is written (Section 3.4).
- Account and model are Employee attributes; the latest values are kept. Recording their changes as history is not implemented (Section 9).
- `alias` (Employee display name) is set per `agent_id` in the `aliases` mapping of the Branch configuration (Section 3.5) and is null otherwise. The Web UI shows it in place of the default name.

#### Seat assignment

When a new agent process is observed, the Employee is selected in this order:

1. The Employee who last worked on the resumed session (including resume under a different account). A session id is kept only in the history of the Employee who last worked on it; each Employee keeps its last 20.
2. The Employee matching the previous runtime location (e.g. tmux pane).
3. The Employee with the lowest free seat number.

A candidate already on shift is skipped and the next rule applies. Candidates are Employees of the same Project and provider. When none remains, a new Employee is created with the lowest seat number that no Employee of that provider on the Host holds.

A roster written before seats were unique per provider on the Host may hold duplicate numbers. At start the first Employee of each number, in roster order, keeps it; the others take the lowest free numbers.

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
- Child-process agent (e.g. Claude launching `codex exec` from its shell): identified by PID and process start ticks; the nearest observed ancestor is resolved through intermediate shell processes. It is a Contractor of that ancestor's root Employee, with `origin: child_process`. If the parent is observed later, the independent Employee shift ends and its ID and history remain off duty; the current child activity and existing Contractors move to the parent's root Employee. Established parent assignment remains fixed and is never inferred from a working directory alone.
- A process relationship needs a process-backed parent observation. Codex app-server threads expose no PID, so a shared daemon alone cannot identify which loaded thread launched a child; that relationship remains unassigned.
- A Contractor's lifetime does not exceed its parent's.

### 1.6 Condition

- Derived from model and runtime settings (e.g. effort level, fast mode).
- The mapping is the `conditions` list of the Branch configuration (Section 3.5); rules match `provider`, optionally `model` (shell-style pattern), `effort`, and `fast_mode`.
- Unmapped combinations use the `normal` condition.
- Default rules, in order:

````yaml
conditions:
  - {provider: claude, fast_mode: true, condition: extra-coffee}
  - {provider: "*", effort: high, condition: study-mode}
  - {provider: "*", effort: xhigh, condition: study-mode}
  - {provider: "*", effort: low, condition: light}
````

- Adapters report `effort` only. No Adapter reports `fast_mode`, so the `extra-coffee` rule does not match observed data yet (Section 9).

### 1.7 Handover Between Providers

- When work moves to a different provider in the same Project by separate invocation, no handover relationship is recorded.
- The Project timeline shows the events in time order.

### 1.8 Branch and Project Lifecycle

| Event | Result |
|---|---|
| Host heartbeat lost | Branch unreachable. Employee states are retained and marked unverifiable. |
| Host heartbeat restored | Branch reachable. Observation resumes. |
| Owner closes a Branch or Project at HQ | HQ record is closed. No command is sent to any Branch; observed Employees keep their presence and activity. |
| Agent observed in a closed Branch or Project | A newly accepted on-duty report reopens the Branch and Project. HQ publishes the transition and can notify viewers. |

HQ owns lifecycle independently of Collector snapshots. A Project has one lifecycle across all Branches. Existing records start open; closing a Branch does not close its Projects. Repeated closure is idempotent, and unknown targets are rejected.

Reopening qualifies in HQ acceptance order after closure: an on-duty `agent`, an `activity` matching its current on-duty instance, or an accepted `snapshot` containing an on-duty agent. Idle agents qualify. Heartbeats, Branch metadata, off-duty reports, duplicates, stale messages, and rejected batches do not qualify. An unchanged idle Collector poll emits only a heartbeat and leaves closure intact.

HQ records closure and reopening at its receive time. Old `event_at` or skewed `sent_at` values do not prevent a newly accepted report from reopening a record. Activity facts retain their existing timestamps. Lifecycle persists across restart, checkpoints, and retention; closure does not change work-log measurements. [The lifecycle decision](decisions/ADR-20261022-hq-lifecycle.md) defines ownership and access.

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
| `thinking` | Explicit model-generation signal. Not inferred when the provider emits none. Not produced by the current Adapters (Section 3.4). | Desk | Thought bubble; posture chosen randomly per occurrence (chin on hand or leaning back) |
| `waiting` | Explicit user-input or approval request. | Desk | Waving hand. No time-based transition. Browser notification from the Web UI (Section 6.4). |
| `idle` | Alive, no active turn. | Section 2.3 | Section 2.3 |
| `completed` | Provider turn-completed event. | Desk | Momentary checkmark, then `idle` |
| `error` | Agent-level failure (API error, authentication failure, abnormal halt). Normal process exit is not an error. | Infirmary | Browser notification from the Web UI (Section 6.4) |
| `limited` | Provider usage-limit event, including a turn that ends with a usage-limit error. | Desk | Computer off, watching wall clock. Reset time shown on the clock when available. No time-based transition. No browser notification. |
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

- Workload is the number of tool executions started in the last 5 minutes (fixed window) of the current shift, sent as `workload` in `activity`.
- Workload is recomputed on every Collector tick; a change caused only by time (an execution leaving the window) is sent as a new `activity`, so an Employee without new tools falls to 0 after 5 minutes.
- The Web UI shows it as "N recent tools".
- A monitor count on the desk that scales with workload, and a per-Branch window and mapping, are not implemented (Section 9).

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
- An unreadable roster starts empty and is kept aside (Section 3.6).

### 3.2 Observations

An Adapter emits only the observations its provider exposes.

| Observation | Content | Used for |
|---|---|---|
| `process.started` | pid and process start ticks when available, working directory, runtime location, highest confidence its sources support; parent PID is resolved locally through the process table | On duty, Project, seat assignment |
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
- A provider usage-limit error reports `limit.reached`, not `agent.error`. `limited` persists through `turn.completed` and `idle` status. It clears on `limit.cleared` (to `idle`), `turn.started`, `tool.started`, or `active` status. `reset_at` is sent while `limited`.
- The Collector gathers one tick's observations before the Judge assigns Employees. Known shifts that end are processed before replacements, new process-backed parents start before descendants, and other observations retain their order. Child activity uses the same state logic as Employee activity but emits Contractor payloads instead of a second Employee. A child's in-process subagents also belong to the root Employee; all end with that Employee's shift.

### 3.3 Reading

- Logs are read incrementally from the last position (inode, offset) on every tick.
- A transcript with no stored position is read from its end when attached; history before attach is not replayed. A transcript created after attach is read from its start; a resumed one (Claude: first record older than attach; Codex: thread `createdAt`, or for a rollout-only shift the `session_meta` `timestamp`, older than attach; either: already followed earlier in the run) is read from its end.
- Attaching in the middle of a line resumes at the next line. A line that is not valid UTF-8 JSON is skipped.
- An unreadable `roster.json` is reported once on standard error with its path and reason (Section 3.6).
- A transcript or rollout that cannot be read is reported and skipped for that poll without affecting other shifts. A JSON-RPC error on one Codex `thread/read` skips that thread for the poll; transport errors reconnect.
- At attach, model and effort are taken from the last non-error assistant record in the transcript tail.
- A session file that exists but cannot be parsed keeps the current shift; a shift ends only when its file is gone or its process is not alive.
- Liveness: `/proc/<pid>/stat` exists, the process is not a zombie, and field 22 (start time in clock ticks) equals `procStart`.
- Rotation, truncation, and partial trailing lines are handled.
- Raw observations are not persisted.
- Basic observation never modifies agent configuration. Hooks are optional enhancements.

### 3.4 Provider Sources

Provider structures: Claude Code 2.1.303, Codex CLI 0.163.0 (app-server 0.162.1 / 0.163.0), and Antigravity CLI 1.4.5. Antigravity presence locks and transcript field structure are observed on a live host; state transitions are covered by synthetic fixtures.

#### Claude Code

| Purpose | Source |
|---|---|
| Live sessions, shift | `~/.claude/sessions/<pid>.json` (`pid`, `procStart`, `sessionId`, `status`, `statusUpdatedAt`, `cwd`, `tmux` as `<session name>:@<window id>.%<pane id>`, `kind`). Equivalent view: `claude agents --json`. |
| Shift identity | `(pid, procStart)` |
| Detail | `~/.claude/projects/<encoded-cwd>/<sessionId>.jsonl` |
| Turn completed | `system` record, `subtype: turn_duration`; `assistant` `stop_reason: end_turn` |
| Thinking | `assistant` content item `thinking` (`thinking`, `signature`); record-level `thinkingDurationMs` (integer ms, usually present). The record is written after the block completes. |
| Tool | `tool_use` (`id`, `name`) → `tool_result` (`tool_use_id`, `is_error`) |
| Waiting | `sessions/<pid>.json` `status: waiting` with `waitingFor` present; cleared on decision. Not recorded in transcripts while open (trailing `tool_use` without `tool_result`). Outcome afterwards: `permissionDecision` (accept) or `toolDenialKind` (deny). |
| Session status values | File: `idle`, `busy`, `shell`, `waiting`. `claude agents --json`: `status` as above or `null`; `state`: `working`, `blocked`, `null`. |
| Usage limit | `assistant` record with `isApiErrorMessage` and a top-level `quotaLimits` object: `status`, `rateLimitType`, `resetsAt`, `isUsingOverage`, `overageStatus`, `overageDisabledReason`, `unifiedRateLimitFallbackAvailable`. The session file has no limit field. |
| Error | `assistant` record with `isApiErrorMessage`, `message.stop_reason: stop_sequence`, one `text` content block, top-level `error` (short snake_case string), optional `apiError` (string), `apiErrorStatus` (integer), `errorDetails` (string) |
| Model, effort | `requestedModel`, `effort`, `perTurnEffort`; `attachment` `type: model` |
| Resume | `--resume` and `--continue` keep the same `sessionId` and append to the same file. |
| Fork | `--fork-session` creates a new `sessionId` with no reference to the origin. |
| Continuation | `continued-in` record in the old file (`continuedInSessionId`) |
| Contractor | `tool_use` `name: Agent` → `toolUseResult.agentId`; `<sessionId>/subagents/agent-<agentId>.jsonl` and `.meta.json` (`toolUseId`); subagent records carry the parent `sessionId` |
| Project | `cwd`, `gitBranch` on records |
| Account | Claude home (one configuration directory per account) |

- Contractor: an `Agent` `tool_use` hires one, keyed by its `id`; the matching `tool_result` ends it, unless its subagent transcript is still active (a background run), in which case it ends when that transcript reaches `idle` or `error`. The subagent transcript is the `agent-*.jsonl` whose `.meta.json` `toolUseId` matches; it is read from its start. Its `tool_use` sets the tool, `tool_result` clears it, and `stop_reason: end_turn` or `turn_duration` sets `idle`. Without that file the Contractor is `working` with no tool. A session change ends open Contractors.
- Usage limit: an `isApiErrorMessage` record carrying `quotaLimits` reports `limit.reached` instead of `agent.error`, with `reset_at` from `resetsAt` read as epoch seconds, epoch milliseconds, or ISO 8601; any other value gives no reset time. Other `isApiErrorMessage` records report `agent.error`. Error strings and other `quotaLimits` fields stay on the Branch.
- Thinking: the record holding a `thinking` block is written only after the block completes, and the session file shows only `busy` meanwhile, so live thinking is not observable and `thinking` is not produced.

#### Codex

| Purpose | Source |
|---|---|
| Live threads, shift | App-server daemon per Codex home. The Collector connects to `<codex-home>/app-server-control/app-server-control.sock` (the `socketPath` that `<launcher> app-server daemon version` reports) and speaks JSON-RPC over WebSocket: the `initialize` request and `initialized` notification, then `thread/loaded/list` and `thread/read`. |
| Runs outside the daemon | Rollout files under `<codex-home>/sessions/*/*/*/rollout-*-<thread-id>.jsonl` written within the last 30 minutes, whose thread the daemon does not know |
| Shift identity | Thread `id` while its status is not `notLoaded`; for a run outside the daemon, `rollout:<thread-id>` while its rollout is written within 30 minutes |
| State changes | Notification `thread/status/changed` (`threadId`, `status`). Delivered to a passive client that only lists and reads; no subscription required. Turn and item notifications are not delivered to such a client. |
| Thread status | `notLoaded`, `idle`, `systemError`, `active` with `activeFlags`: `waitingOnApproval`, `waitingOnUserInput` |
| Turn | `turn/started`, `turn/completed` |
| Tool | `item/started`, `item/completed` |
| Detail | `<codex-home>/sessions/YYYY/MM/DD/rollout-<timestamp>-<uuid>.jsonl` |
| Usage limit | rollout `event_msg` `token_count` (`type`, `info`, `rate_limits`); `rate_limits` may be null, else `credits`, `individual_limit` (null), `limit_id`, `limit_name`, `plan_type`, `primary`, `secondary`, `rate_limit_reached_type` (null), `spend_control_reached` (null); `primary` and `secondary` are null or `used_percent` (float), `window_minutes` (integer), `resets_at` (epoch seconds) |
| Error | status `systemError`; rollout `task_complete.error`, an object `codex_error_info` (string; observed `usage_limit_exceeded`, `server_overloaded`) and `message` (string), or a plain string in older rollouts |
| Reasoning | Retrospective only: rollout `response_item` `type: reasoning`; `event_msg` `item_completed` with `item.type: Reasoning` |
| Model, effort | rollout `thread_settings_applied`, `turn_context` |
| Resume | Same session id; appends to the same rollout file. |
| Fork, Contractor | Thread `forkedFromId`, `parentThreadId`; `state_5.sqlite` `thread_spawn_edges`; rollout `session_meta` `source` (subagent) and `parent_thread_id` |
| Project | Thread `cwd`, `gitInfo`; rollout `session_meta` `cwd` |
| Account | Codex home (one daemon per home) |

- No pid is exposed by Codex logs, sqlite state, or app-server responses.
- The Collector acts as a read-only app-server client. After the `initialize` / `initialized` handshake (client name `agentville`, its version, `experimentalApi: false`), only `thread/loaded/list` and `thread/read` are called; no method that starts, resumes, sends to, or interrupts a thread.
- Only loaded threads are read. Reading a `notLoaded` thread is avoided until its side effects are verified.
- `thread/loaded/list` and `thread/read` seed state on connect and after reconnect; afterwards state follows `thread/status/changed`. `optOutNotificationMethods` is never set for it.
- Turn and tool detail come from the thread's rollout file, not from app-server notifications. Reasoning is recorded only after it completes and a passive client receives no item notifications, so `thinking` is not produced.
- Threads that are not Employees: subagent threads (`parentThreadId` set or `source.subAgent`), and `threadSource: system` (internal threads, typically with a null `path`, ignored).
- A loaded subagent thread is a Contractor of the shift of its `parentThreadId` (for a nested subagent, the root shift; seeds read parents before their subagents at any depth); one whose parent is not a shift is not tracked. State follows its thread status (`active` → `working`, `waitingOn*` → `waiting`, `idle`, `systemError` → `error`); the tool comes from its rollout. It ends when the thread is closed, `notLoaded`, absent at a seed, or when the parent shift ends.
- A `token_count` with any window at `used_percent` ≥ 100 reports `limit.reached` with the latest `resets_at` of those windows; a later one with every window below 100 reports `limit.cleared`.
- `task_complete.error`: `codex_error_info: usage_limit_exceeded` is not an error; the shift stays `limited`, or, when no full window was seen, reports `limit.reached` with the `resets_at` of the most used window of the latest `token_count` (none when unknown). `server_overloaded` is transient: the turn completes without `agent.error`. Any other kind, and a plain-string error, report `agent.error`. The error text is not sent.
- Rollout path: `Thread.path`; when null, `<codex-home>/sessions/*/*/*/rollout-*-<thread-id>.jsonl`.
- Responses carry no `jsonrpc` field; the client does not require it. Server-to-client requests (approvals) are never answered.
- On loss of the app-server connection, every Codex shift and Contractor is reported `unknown` until the next seed.
- Codex runs that do not use the shared daemon (e.g. IDE extension, `codex exec`) are observed from rollout files only, as rollout-only shifts:
  - Each poll lists `<codex-home>/sessions/*/*/*/rollout-*-<thread-id>.jsonl` and takes the files modified within the last 30 minutes whose thread is not known from the app-server (loaded, ignored, a Contractor, or a shift). At attach, a pre-existing rollout needs a matching live process; otherwise its file version is retained and it starts no shift until the file changes. This prevents completed children appearing as colleagues after a Collector restart or container rebuild. A thread whose daemon or rollout-only shift or Contractor ended is taken only after its rollout is written again.
  - Rollout ownership first uses a unique codex process holding the rollout open. Descriptor discovery examines only codex processes. When that evidence is unavailable, the match requires a unique codex process whose start is within five seconds before rollout creation (with one second of clock rounding tolerance); an available process working directory must agree with the rollout. An inaccessible working directory does not rule out an otherwise unique start-time match. Ambiguous matches remain unassigned. PID and start ticks are checked again by the Judge before using ancestry.
  - The rollout's `session_meta` record (within its first 5 lines) gives `cwd`. A rollout whose `session_meta` is not yet complete is retried on the next poll; one without it is skipped. Subagent rollouts (`source` naming a subagent, or `parent_thread_id` set) and `thread_source: system` are skipped, as for app-server threads.
  - The shift is `rollout:<thread-id>` with runtime `{"type": "rollout"}`, the account alias of the Codex home, source `session_log`, and confidence `low` for every state.
  - Reading follows Section 3.3: a rollout found at attach is read from its end; one created after attach is read from its start; one that an earlier rollout-only shift of this run followed continues from its last position, and one followed only by a daemon shift is read from its end.
  - State comes from the rollout records as for daemon threads: `task_started`, tool calls and outputs, `task_complete` with the error and limit rules below, `token_count` limits, model and effort. No live status exists, so `waiting` is not produced and a shift found at attach is `unknown` until its next turn or tool record.
  - A process-backed shift ends (`process.exited`) when that process exits or its PID has a different start time. A rollout-only shift also ends when the rollout has not been written for 30 minutes or is gone. When the daemon later reports the same thread, the rollout-only shift ends and the daemon shift starts in the same poll, continuing the rollout from the same position; seat rule 1 returns it to the same Employee.

#### Antigravity CLI

| Purpose | Source |
|---|---|
| Live sessions | `<gemini-home>/antigravity-cli/presence/<conversation-uuid>.lock`, matched by device and inode to a held kernel lock in `/proc/locks`, owned by a live `agy` process |
| Shift identity | Conversation id, owning PID, and process start ticks |
| Project | Owning process working directory; Common Office if unavailable |
| Detail | `<gemini-home>/antigravity-cli/brain/<conversation-uuid>/.system_generated/logs/transcript.jsonl`; `created_at`, `step_index`, `type`, `source`, `status`, `tool_calls` |
| Turn | `USER_INPUT` from `USER_EXPLICIT` starts work; a `PLANNER_RESPONSE` from `MODEL` without tool calls and with `DONE` completes the turn; `RUNNING` starts work |
| Tool | A `GENERIC` from `MODEL` carries `tool_calls` (`name`, `args`); `RUNNING` starts each step/index once, `DONE` or `ERROR` finishes it. Arguments and output are ignored. |
| Error | `ERROR_MESSAGE`, or a `PLANNER_RESPONSE` without tool calls and with `ERROR`. Tool errors remain work. |
| Account | Configured Gemini home containing `antigravity-cli`; separate from Gemini CLI account inference |

- The Adapter reports `working`, `completed` followed by `idle`, `error`, or `unknown`, capped at medium confidence. It produces no `thinking`, `waiting`, or `limited` activity without an identified live signal. All documentation uses this state set.
- At attach, the latest supported complete record in the transcript tail seeds activity, without replaying tool counts or historical turns. Complete historical records are fingerprinted once from activity fields and tool names; only their SHA-256 digests are retained, excluding content and tool arguments. The shift retains these digests until it ends so rotation or truncation cannot replay an already observed record. Subsequent new records are read incrementally; tool completion clears the tool name. A stale lock file without an owning live process produces no colleague. Loss of the held lock or process ends the shift.
- Existing configurations need `providers.antigravity` enabled explicitly. First-start discovery examines `~/.gemini` and `~/.gemini-*` only when they contain `antigravity-cli`. These names overlap Gemini CLI homes and are not account identity evidence by themselves.

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
  antigravity:
    - {home: ~/.gemini, account_alias: antigravity-account-1}
conditions:
  - {provider: claude, fast_mode: true, condition: extra-coffee}
  - {provider: "*", effort: high, condition: study-mode}
  - {provider: "*", effort: xhigh, condition: study-mode}
  - {provider: "*", effort: low, condition: light}
collector: {poll_interval: 1.0, heartbeat_interval: 30}
aliases: {}
````

- `aliases` maps an `agent_id` to an Employee display name, sent as the agent `alias`. Each name is a non-empty string of at most 40 characters. The Web UI shows the `agent_id` in the Colleague detail.
- `time` is the host's local zone at first start (`TZ`, `/etc/timezone`, or the `/etc/localtime` link; `UTC` when none is found).
- One provider home is one account. At first start, `~/.<provider>` and existing `~/.<provider>-*` directories are listed in that order as `<provider>-account-1`, `<provider>-account-2`, …; `~/.claude` is always listed. Account names and homes are local settings.
- A single mapping (`claude: {home: ~/.claude}`) is read as a one-account list.
- The generated file lists provider homes as absolute paths with the home directory expanded; `~` is accepted when editing.
- Values are validated at start: `host`, `hq`, `thresholds`, `providers`, `collector`, and `aliases` are mappings, each `providers` entry a list (or the single-mapping form), `conditions` a list of mappings; thresholds are integers >= 0 with `phone` <= `doze` <= `lounge`; `poll_interval` > 0; `heartbeat_interval` >= 1. A file holding `hq.token` must not be accessible by group or others.
- An invalid file, including a YAML syntax error or a top level that is not a mapping, stops the Collector with one line `agentville-collector: invalid configuration: <reason>`; one that cannot be read or created with `agentville-collector: configuration <path>: <reason>`.
- A loopback HQ is contacted without environment proxies.
- Condition rules are evaluated in order; the first match wins; `model` accepts shell-style patterns. The defaults are listed in Section 1.6. A configuration without a `conditions` key uses them; an empty list maps everything to `normal`.

### 3.6 Run Loop

- A tick runs every `collector.poll_interval` seconds (default 1.0). Each tick polls every Adapter, applies observations to the Judge, and emits messages.
- The first tick emits a `snapshot` instead of individual changes. A `heartbeat` is emitted every `heartbeat_interval`.
- `seq` is reserved in blocks of 1000 in `$XDG_STATE_HOME/agentville/seq` (default `~/.local/state/agentville/seq`), written with fsync before use; a restart resumes after the reserved bound.
- A failing Adapter is logged to stderr and skipped for that tick; other Adapters continue.
- At start, an unreadable `roster.json` (invalid JSON, not a list, or a read error) is logged as one line to stderr naming the file and the reason, and the roster starts empty. Before the next roster is written, the unreadable file is moved to `roster.json.bad`, replacing an earlier one. A missing roster starts empty silently.
- Time-based presence changes (off duty to on leave) are emitted when the threshold passes, without a new event. Likewise, a workload change caused only by time is emitted as `activity` (Section 2.5).
- Services: `deploy/systemd/agentville-collector.service` and `deploy/systemd/agentville-hq.service` (systemd user units).

## 4. HQ

- Process: `agentville-hq` (FastAPI, uvicorn), bound to `127.0.0.1:8470` by default.
- `--tls-cert` and `--tls-key` (PEM files, used together) make HQ serve HTTPS directly; without them HQ serves plain HTTP.
- At start HQ checks its token files, the notification configuration (Section 4.6), and TLS certificate and key (loaded into a TLS context), opens the database, and binds and listens on the port itself (`SO_REUSEADDR`, IPv6 when the host contains `:`), handing the socket to uvicorn. Only then does it print `agentville-hq: serving <scheme>://<host>:<port>/ (database <path>)` to standard error.
- A missing or unreadable token file, a malformed token file, an invalid notification configuration, an unusable certificate or key, a database that cannot be opened, or a port that cannot be bound stops HQ with one line starting with `agentville-hq:`, e.g. `agentville-hq: cannot listen on 127.0.0.1:8470: Address already in use`.
- `agentville-hq --version` and `agentville-collector --version` print the installed package version, which HQ also reports as its API version in `/openapi.json`.
- Storage: SQLite (WAL) at `$XDG_DATA_HOME/agentville/hq.sqlite3` (default `~/.local/share/agentville/hq.sqlite3`).

| Table | Content |
|---|---|
| `messages` | Every accepted message, keyed by `(branch_id, seq)` |
| `branches` | Branch payload, last `seq`, last seen time, heartbeat interval |
| `agents`, `activities`, `contractors` | Current state, keyed by `(branch_id, id)` |
| `lifecycles` | HQ-owned Branch and Project records; Branch key `(branch_id, "branch:" + id)`, global Project key `("", "project:" + id)` |
| `changes` | Every change HQ applies to current state: `(branch_id, at, kind, key, payload)`, `payload` NULL for a removal (Section 4.4) |
| `baseline` | State as of the start of the kept history, keyed by `(branch_id, kind, key)` |
| `checkpoints`, `checkpoint_keys` | State at whole hours (UTC): each key with the id of its latest change, or NULL for its `baseline` payload (Section 4.4) |
| `meta` | `history_from`: the start of the kept history |

- Retention: 30 days by default (`--retention-days`), applied at most once per hour during ingest. Messages received before the cutoff are deleted, and history changes and checkpoints before it are folded into the baseline (Section 4.4). Current state is never pruned.
- Ingest, pruning, and the live state use one connection under one lock. History reads (Sections 4.4 and 4.5) use separate read-only connections, each in one read transaction and used by one query at a time; WAL lets them read while ingest writes, so they never wait for ingest and ingest never waits for them.
- Write-ahead log: ingest never checkpoints the log itself (`wal_autocheckpoint` 0; `journal_size_limit` 32 MiB). A read transaction keeps the log frames it may need, so overlapping history reads would keep the log from restarting. When the log file exceeds 32 MiB after an ingest, a background thread holds back new history reads, waits for the running ones to finish, copies the log into the database with passive checkpoints (up to five passes, which do not block ingest), then runs a truncating checkpoint under the store lock for the remaining frames, and lets history reads continue. The log thus stays near 32 MiB, exceeding it by what is written while the longest running history read finishes. New history reads wait up to that read's remaining time; ingest and the live state do not wait for reads.
- HQ sets the interpreter's thread switch interval to 0.5 ms, so a long history computation yields often to ingest and the live state.

### 4.1 Ingest Rules

Messages of one batch are applied in `seq` order:

| Case | Result |
|---|---|
| Non-snapshot message whose `(branch_id, seq)` is already stored | Duplicate; ignored, regardless of `sent_at` |
| `snapshot` with `seq` not above the last applied, and a stored message with the same `seq` and the same `sent_at` | Duplicate; ignored |
| `snapshot` with `seq` not above the last applied and `sent_at` earlier than the latest applied `sent_at` | Stale, not applied; response asks for a snapshot |
| Such a stale `snapshot` again, after HQ asked for one following a stale snapshot and applied no message from the Branch since | The Branch's clock moved back: applied as a reset like the next row, and the latest applied `sent_at` is set to its `sent_at` |
| Other `snapshot` with `seq` not above the last applied (Branch lost its sequence state) | Stored messages from that `seq` on are discarded; the snapshot is stored and applied and restarts the numbering |
| `snapshot` | Replaces Collector-owned current state of the Branch; preserves HQ lifecycle |
| `seq` lower than the last applied | Stale; stored, not applied |
| `seq` not equal to last + 1, or no state for the Branch | Applied; response asks for a snapshot |
| `agent` with no instance | Employee updated; its activity removed |
| `contractor` with status `ended` | Contractor removed |

The latest applied `sent_at` is not advanced by a value more than 5 minutes ahead of HQ's clock.

A single delayed snapshot is rejected: HQ remembers in memory that it asked a Branch for a snapshot after a stale one, and forgets it when any message of that Branch is applied. Only a Branch that keeps answering with old-clock snapshots is reset.

A Branch is reported unreachable when no message arrived within three heartbeat intervals (30 s assumed before its first heartbeat), or when none has arrived since HQ started; Branches heard since start are kept in memory.

### 4.2 API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness |
| `POST` | `/api/v1/ingest/messages` | Branch ingest, body `{"messages": [...]}`, one Branch per batch, at most 1000 messages (more: 413) |
| `POST` | `/api/v1/lifecycle/close` | Administrator-only closure with JSON `{"kind": "branch" or "project", "id": "<identity>"}` |
| `GET` | `/api/v1/state` | Branches (with `reachable`), agents, activities, contractors, lifecycles |
| `GET` | `/api/v1/state?at=<time>` | The same for a past time within the kept history (Section 4.4) |
| `GET` | `/api/v1/history` | The kept history: `{"from", "to"}` |
| `GET` | `/api/v1/changes?from=&to=[&branch_id=]` | Activity, presence, reachability, and lifecycle transitions in a period |
| `GET` | `/api/v1/worklog?from=&to=[&branch_id=]` | Seconds per state of each Employee in a period (Section 4.5) |
| `GET` | `/api/v1/branches` | Branches |
| `GET` | `/api/v1/agents` | Agents |
| `GET` | `/api/v1/stats` | Ingest totals since HQ start |

Ingest response: `{"accepted", "duplicates", "stale", "need_snapshot"}`.

If a stored `(branch_id, seq)` has different `kind`, `event_at`, `sent_at`, or decoded payload, the response includes `"warnings": ["shared_host_id"]`. Exact retries do not warn. Sequence and clock resets retain their existing behavior; lost sequence state can also trigger this diagnostic. The Collector logs the shared-identity warning at most once per minute. The warning does not establish that two Collectors exist and cannot distinguish identical messages.

- `lifecycles` contains `branch_id`, `kind`, `id`, `alias`, `branch_ids`, `closed`, `changed_at`, `closed_at`, `reopened_at`, `revision`, and `reopen_count`. A global Project has an empty `branch_id` and retains its known Branch membership.
- Every `GET` under `/api/v1/` is a read endpoint and requires the viewer token when one is set (Section 4.3).
- Times in query parameters are ISO 8601 with an offset (`Z` or `+hh:mm`). A missing, malformed, or offset-less time is answered with 400.
- A time whose UTC form falls outside the representable range (years 1 to 9999) is answered with 400; in ingest such a `date-time` fails schema validation (422).
- `state?at=` answers 400 for a time before `history_from` or after now, and before the first message (`from` null). `reachable` is the value derived for that time (Section 4.4); `last_seq` and `last_seen_at` are those of the last message received by then.
- `history`: `from` is `history_from`, or null before the first message; `to` is HQ's current time.
- `changes` and `worklog` take a period of at most 31 days (`to` after `from`; otherwise 400). The period is clipped to the kept history and to now; the response `from` and `to` are the clipped period. When no part of the period lies within the kept history and before now (or before the first message), `from` and `to` are null and the lists empty.
- `changes` and `worklog` responses are shared: a request with the same `from`, `to`, and `branch_id` as one answered within the last 30 s gets that answer, and identical requests in progress share one computation (at most 32 distinct requests kept). Closure and reopening invalidate cached responses. At most two such computations run at once; further requests wait for a slot without holding a worker thread.
- `changes` returns `{"from", "to", "changes", "truncated", "agents", "branches"}`. Each entry of `changes` is one of `{"at", "kind": "activity", "branch_id", "agent_id", "state", "state_since"}` (a new state or a new `state_since`; tool and workload changes alone are not listed), `{"at", "kind": "presence", "branch_id", "agent_id", "presence"}`, `{"at", "kind": "reachability", "branch_id", "reachable"}`, or `{"at", "kind": "lifecycle", "branch_id", "target_kind", "target_id", "alias", "closed"}`, in time order, after `from` and up to `to`. At most 5000 entries are returned, the latest ones; `truncated` is true when more exist. `agents` holds the last agent payload (as in `state`) of each Employee listed; `branches` the last Branch payloads (`{"branch_id", "branch"}`).
- `worklog` returns `{"from", "to", "rows", "branches"}`; each row is `{"branch_id", "agent_id", "project_id", "project_alias", "provider", "seat", "alias", "seconds", "waits", "longest_wait", "errors", "limits"}`, where `seconds` holds `on_duty`, the eight activity states, and `unobserved`.
- Lifecycle events identify their Branch or global Project; a Branch filter includes global Projects whose known membership includes that Branch. Work-log measurements continue to depend only on observed Employees and reachability.
- An activity transition in `changes` follows the entry rule of Section 4.5: a `state` or `state_since` other than the Employee's last known activity, also across a removal of the activity.

### 4.3 Authorization

- A Branch connecting from loopback needs no token, unless `--no-trust-loopback` is set (required behind a local reverse proxy) or its `branch_id` is listed in the token file; a listed Branch must send its token from loopback too.
- Any other Branch needs a bearer token listed for its `branch_id` in the HQ token file (`--tokens`, YAML mapping of `branch_id` to token, mode 0600, each token a string of at least 16 characters). The Branch sets the same value as `hq.token` in its configuration.
- A caller that is neither trusted loopback nor holding any configured token is rejected before the body is read.
- Ingest rejections: 401 `token required` when a caller that needs a token sends no `Authorization` header; 401 `invalid token` when the token does not match, or when a Branch listed in the token file sends none from trusted loopback. Read endpoints answer 401 `viewer token required`.
- Branch, viewer, and administrator token files are read at start only; HQ is restarted after editing them.
- `--admin-token-file` supplies a mode-0600 token for closure only. It must be ASCII, contain no whitespace, have at least 16 characters, and differ from the viewer token and every Branch token. HQ validates it before opening the database or listening.
- Without an administrator token, closure returns 503 even on loopback. Missing or incorrect administrator authorization returns 401; viewer and Branch tokens cannot close records. An administrator token alone cannot read viewer-protected state or ingest for a protected Branch.
- Closure requires JSON, a body no larger than 4096 bytes, and exactly `kind` and `id`. Invalid content type returns 415, oversized content 413, malformed input 400, and unknown targets 404. A supplied cross-origin `Origin` returns 403 unless it matches the current host or a configured server name.
- Binding to a non-loopback address requires `--allow-remote` and `--viewer-token-file`; read endpoints then require the viewer token, and loopback Branches need tokens too.
- Messages are schema-validated after authorization, including `date-time` formats. Non-finite numbers (`NaN`, `Infinity`) and excessive nesting are rejected. Request bodies are limited to 4 MiB, counted while reading.
- Ingest accepts only `Content-Type: application/json` and rejects requests carrying an `Origin` header, so a web page cannot submit messages through the trusted loopback path.
- On a loopback bind, requests whose `Host` is not `127.0.0.1`, `::1`, `localhost`, the bind address, or a `--server-name` value are rejected (DNS rebinding guard).
- `--server-name` names the public host of a reverse proxy and requires `--no-trust-loopback` and `--viewer-token-file`.
- `WS /ws/v1/live` accepts a browser only when its `Origin` matches the request `Host` or names a `--server-name`. With a viewer token, the socket is accepted and its first message must be `{"type": "auth", "token": "<viewer token>"}` within 5 s; no state is sent before it. The token is never taken from the URL, so it does not reach proxy access logs. Rejected sockets are closed with code 4403 (origin or host) or 4401 (viewer token missing, wrong, or late).
- Ingest responds after storing. Each viewer has its own sender holding only the latest state, with a 5 s send limit; a viewer that exceeds it is disconnected without delaying others.
- The Collector refuses to send a token over plain HTTP to a non-loopback HQ and does not follow redirects.
- On shutdown HQ checkpoints the WAL and closes the database.

### 4.4 State History

- Every change HQ applies to current state is recorded in `changes`: a key whose payload is set to a different value, or a key removed (`payload` NULL). Kinds and keys: `branch` (key empty), `agent` and `activity` (`agent_id`), `contractor` (`contractor_id`), and `lifecycle` (prefixed Branch or global Project id). Lifecycle revisions record closure and reopening; catalog updates retain aliases and Branch membership. Heartbeats, and messages that are duplicates or stale, record nothing.
- A `snapshot` records only the keys it changes or removes. An `agent` without instance records the removal of its activity; a `contractor` with status `ended` records its removal.
- For lifecycle, `at` is HQ receive time, ordered with prior changes of that key. Other kinds use the message `event_at`, or HQ's receive time when `event_at` is later (a Branch clock ahead of HQ's), and never earlier than the previous change of the same key or `history_from`. Ordering one key's changes by `at` therefore keeps the order in which they were applied, and no change is later than its receipt.
- The state at a time T is the baseline overlaid with the latest change of each key at or before T; changes with the same `at` apply in recording order. At the current time it equals the current state.
- Checkpoints: ingest records the state at whole hours (UTC) in `checkpoints` and `checkpoint_keys`: for each key, the id of its latest change at or before the hour, or NULL when that is its `baseline` payload. Each ingest walks the changes after the latest checkpoint in time order; before a change past the next whole hour, it records a checkpoint at the last whole hour before that change. It then records one at the last whole hour at or before the ingest time. Other whole hours get no checkpoint: after a checkpoint at 00:00, changes at 01:10 and 03:05 and an ingest at 05:05 give checkpoints at 01:00, 03:00, and 05:00. A change recorded later with an `at` at or before a checkpoint (a late fact) is the latest of its key there, so it updates every checkpoint from its `at` on. The state at T is computed from the latest checkpoint at or before T (the baseline when there is none) and the latest change of each key after it up to T, so a read costs the changes of at most about one hour plus those of the requested period. A database without checkpoints gets them when HQ opens it.
- `history_from`: a new database starts its history at the receive time of its first message. A database written by 0.1.0 starts it at the first start of 0.2.0: the current state is copied into the baseline then, and no earlier history exists.
- Pruning (Section 4) uses the same cutoff as messages. The baseline becomes the state just before the cutoff (from the latest checkpoint before it and the changes since); checkpoint keys whose change is before the cutoff are set to NULL, whose baseline payload is now that change's; checkpoints and changes before the cutoff are deleted and `history_from` moves to the cutoff.
- Reachability at a past time comes from `messages`, not from `changes`: a Branch is observed at T when the last message received at or before T arrived within three heartbeat intervals before T (the interval of the latest `heartbeat` received by then; 30 s before the first). A gap between received messages longer than that is unobserved. The live rule that a Branch not heard since HQ started is unreachable (Section 4.1) does not apply to past times. Messages discarded when a Branch lost its sequence state (Section 4.1) shorten this record.

### 4.5 Work Log

`GET /api/v1/worklog` sums, for each Employee `(branch_id, project_id, agent_id)`, the time within the period:

| Field | Content |
|---|---|
| `seconds.on_duty` | Presence `on_duty` while the Branch is observed. |
| `seconds.<state>` | Each of `working`, `thinking`, `waiting`, `idle`, `completed`, `error`, `limited`, `unknown` while on duty and observed; on duty without an activity counts as `unknown`. Together they equal `on_duty`. |
| `seconds.unobserved` | Branch gaps (Section 4.4) while the Employee's last known presence is `on_duty`. |
| `waits`, `errors`, `limits` | Entries into `waiting`, `error`, and `limited` at a time within the period: an activity in that state whose `state` or `state_since` differs from the Employee's last known activity: the latest activity recorded up to then, also one removed before or within the period. An activity removed and restored with the same `state` and `state_since` is not a new entry. |
| `longest_wait` | The longest single wait: observed seconds of one `waiting` `state_since`. A wait across a Branch gap stays one wait without the unobserved time. |

- Total waiting time is `seconds.waiting`.
- Intervals are clipped to the period; a wait that began before it counts its time within the period but no entry.
- Rows are listed only for Employees with on-duty or unobserved time, or an entry, in the period. Each row carries the Employee's last agent payload fields `project_alias`, `provider`, `seat`, and `alias`.
- Contractors are not included.

### 4.6 External Notifications

With `--notify-config <file>`, HQ posts the notifications of Section 6.4 to an ntfy topic, so they reach a subscribed phone or desktop without an open page. Off by default.

Configuration file (YAML, mode 0600 required, read at start only):

| Key | Content |
|---|---|
| `url` | ntfy topic URL. `https` required unless the host is loopback; the path names the topic. |
| `token_file` | Optional. File holding an access token (mode 0600), sent as `Authorization: Bearer <token>`. `~` is expanded. |
| `events` | Optional list of `waiting`, `error`, `branch`, `reopened`; default all four. An explicit list enables only its listed events. |
| `language` | Optional, `en` (default) or `ko`. |

- Other keys, a wrong value, an unreadable or group- or other-accessible file, or an empty token file stop HQ at start with one line `agentville-hq: <file>: <reason>`.
- Rules, as in the browser (Section 6.4): a colleague entering `waiting` or `error` (a new `state_since` in the same state counts as a new entry), and a Branch becoming unreachable or reachable again. Nothing is sent for the first evaluation after HQ starts, for a colleague or Branch seen for the first time, or for colleagues of a Branch whose ingest applied a snapshot (a resync). A Branch takes part only once it has been heard since HQ started, so Branches reporting again after an HQ restart are not announced.
- `reopened` notifies actual Branch or Project reopening, including reopening caused by an accepted Collector snapshot. HQ seeds persisted lifecycle counters before ingest starts, so restart itself does not notify and the first qualifying report can notify. Snapshot suppression of colleague alerts does not suppress reopening.
- Evaluation runs after each ingest and every 5 s, since reachability changes with time alone. Evaluations run one at a time; each reads the current state together with the Branches whose snapshot was applied since the previous evaluation, which ingest records in the same locked step that applies the snapshot. Whichever evaluation first sees a snapshot's state therefore treats it as a resync.
- Rate limit: at most one message per subject per 30 s; a change inside that window is held and sent at the first evaluation after it ends, only if the subject is still in that state and it differs from what was last sent. When more than three subjects qualify in one evaluation, one summary is sent instead.
- Texts are the browser notification texts, read from the Web UI dictionary (`web/i18n.js`) in the configured language.
- Request: `POST` to `url`, body the text (`text/plain; charset=utf-8`), headers `Title`, `Tags` (`agentville,<event>` with event `waiting`, `error`, `unreachable`, `reachable`, `reopened`, or `summary`), and `Priority` (`default` for waiting, reporting again, and reopening; `high` for error and unreachable; a summary takes `high` when it includes either). A non-ASCII title is sent as an RFC 2047 encoded word (`=?UTF-8?B?...?=`); control characters become spaces. Redirects are not followed; a loopback server is contacted without environment proxies.
- Sending runs in one background thread with a queue of 100 messages and a 10 s timeout per request. A message that does not fit is dropped. Failures are logged to standard error as `agentville-hq: notification failed: <reason>`, at most once per minute. Ingest never waits for sending.

## 5. Transport

- The Collector sends each tick's messages as one batch by HTTP(S) POST to `hq.url`. Remote Branches connect outbound only; HQ never connects to a Branch.
- On delivery failure the batch is dropped and the next successful delivery starts with a snapshot. Failures include HTTP errors, connection and TLS errors, and responses cut short or malformed (`http.client` exceptions such as `IncompleteRead`, `RemoteDisconnected`, `BadStatusLine`); none ends the Collector. Retries back off from 1 s to 60 s.
- When HQ reports `need_snapshot`, the next tick sends a snapshot.
- `agentville-collector --output <path|->` writes JSONL instead of sending, for diagnostics. It reads the `seq` and `roster.json` state files but never writes them.
- At start the Collector prints `agentville-collector: Branch <alias> (<host.id>) reporting to <hq.url or output>` to standard error. An unusable `hq.url` (unsupported scheme, or a token over plain HTTP to a non-loopback host) stops it with a message.

## 6. Web UI

- Navigation: Virtual office, Dashboard, Colleagues, Projects, Timeline, Work log, Branches, and display settings.
- Remote Employees of the same Project appear in the same Room with a Branch `alias` badge.
- Interface terms. The domain model keeps its names; only the visible labels differ. Employee is shown as "Colleague" (동료) everywhere in visible text, including headings, navigation, search, table headers, empty states, and accessible names; internal names and payload fields (`agent`, `agent_id`) are unchanged. Other labels: Branch (지점), HQ (본사), Room (방; each Project room carries a small "repository" / "저장소" sublabel, since one repository is one room; the Common Office carries none), Common Office (공용 사무실), Lounge (Fika) (휴게실 (Fika)), Infirmary (양호실), Contractor (외주), Seat (자리), Work log (근무 일지), Replay (되감기), waiting time (대기 시간).
- Presence labels: On duty (출근), Off duty (퇴근), On leave (휴가). Activity labels: Working (작업 중), Thinking (생각 중), Waiting (대기), Idle (유휴), Closed (닫힘) for `completed`, Error (오류), Limited (한도), Not measured (재지 못함) for `unknown`. Connection labels: Unverified (확인 안 됨), Waiting for Branch report (지점 보고 대기), Not connected to HQ (HQ 연결 끊김). The label Closed (폐쇄) is reserved for a closed Branch or Project (Section 1.8), distinct from the `completed` activity label. Idle details: At desk (자리에서), Phone (휴대폰), Dozing (조는 중), Fika (휴게실). Conditions: Normal (보통), study-mode (집중), extra-coffee (커피 추가), Light (가볍게); the legacy value `lazy` is shown as Light and keeps the same pose.
- Copy is plain and factual: interface text states what is shown or what to do, without slogans, decorative captions, or exclamations. Labels use noun phrases; Korean sentences use 합니다체.
- Language: English and Korean. Every visible string, including accessible names, titles, and alternative text, comes from one dictionary in `i18n.js` through a `t(key, params)` helper. The display settings offer English / 한국어. The default follows the browser language (Korean when it starts with `ko`, otherwise English); the choice is kept in local storage when available. Switching re-renders the page in place and sets `<html lang>`. Dates and times use the matching locale (`en-US` or `ko-KR`) with the Branch time-zone rules below. Branch-provided text (Branch, Project, and Employee aliases, locations, tool names) is never translated.
- Employee name: the `alias` when set, otherwise the provider name and seat ("Codex 2"); seats are unique per provider on a Branch (Section 1.4). The same name is used in the office, lists, tables, the Timeline, the Work log, and notifications.
- Provider labels include Antigravity with initials `AG`. Branch aliases that collide include the full Branch id, including colleague detail, selectors, and work-log group headings.
- Employee detail: current activity, condition, tool name, workload, Project, Branch alias, usage-limit reset time when known, waiting time of the browser day ("Waited today", duration and number of waits, from the work log; not shown while replaying), the `agent_id` in small monospace text for use in the Branch configuration `aliases`, and the Employee's Contractors with provider badge, activity, and tool name.
- Status filters and Branch indicators highlight waiting Employees, errors, and unverified connections.
- Employee detail ends with factual notes only: the reason for an unverified, limited, or unmeasured state, and "Last observed" with the time of the Branch's last report.
- Visual style: Cyworld-inspired isometric minirooms with chibi pixel characters, as inspiration only; original artwork, no copied graphics or brand assets.

### 6.1 Workspace and live data

- Served by HQ at `/` (static HTML, CSS, JavaScript, and bundled artwork; no build step). The initial view is the virtual office.
- Live data: `WS /ws/v1/live` sends `{"type": "state", "state": ...}` (the `/api/v1/state` shape) on connect, after ingest (bursts coalesced), and every 10 s. The page reconnects with backoff up to 30 s.
- With a viewer token, the page reads it from the URL fragment (`#token=...`), keeps it in session storage, and removes it from the address bar (`history.replaceState`; no page module declares a top-level name that shadows a window global such as `history`, `location`, or `name`). On each socket open the page sends `{"type": "auth", "token": ...}` as its first message (`null` without a token); HQ without a viewer token ignores it.
- Close code 4401 shows that a viewer token is required and 4403 that HQ refused the connection; neither is retried.
- A Branch not heard since HQ started is reported unreachable, so the page shows "Waiting for Branch report" until its first message after an HQ restart.
- Idle detail (at desk, phone, dozing, fika) is computed in the page from `state_since` and the Branch thresholds.
- Branch-provided text is rendered as text only, never as markup.
- History (Timeline, replay, Work log, waiting times) is read with `fetch` from the read endpoints of Section 4.2; with a viewer token the page sends it as `Authorization: Bearer`, never in a URL. The page reads `/api/v1/history` at load and every 60 s.

### 6.2 Virtual office presentation

- The floor combines `office.png` with textured Employee and cat atlases rendered by `art.js` and `sprites.js`. Artwork generation inputs and asset paths are recorded in `design/office-artwork.prompt.txt` and `design/character-artwork.prompt.txt`.
- Twelve Employee appearances combine hair colors, glasses, hats, and headphones. The complete roster receives balanced assignments before filtering, and existing assignments remain stable during the browser visit. Each appearance has matching standing, seated, rear-facing, and reclining sprites; `*-varied.png` atlases supply the six additional appearances, with generation inputs recorded in `design/employee-appearance.prompt.txt`.
- Each Project occupies one room. The office displays two Project rooms at a time; room navigation exposes additional Projects. Common Office, Fika, and the infirmary remain available.
- Employees from another Branch appear beside local Employees of the same Project, with a Branch alias badge. Contractors stand beside their parent, independently of the parent's seated, reclining, or coffee pose. A Contractor is drawn at about three quarters of an Employee's size and wears a safety-yellow hard hat with a dark outline, drawn in code in the same pixel style; a persistent tag with the provider initials (CL, CX) sits beside the figure, so Contractors are recognizable without hovering at the default zoom on wide and narrow screens. Each shown Contractor takes the pose and state mark of its own activity (an absent or unrecognized state shows as `unknown`), and its label shows the provider badge, activity, and tool name while `working`. Up to two Contractors are drawn per Employee; the last one drawn carries a yellow "+N" count of the remainder beside its hat.
- Activity controls character gestures. Idle thresholds select desk, phone, dozing, or Fika presentation; errors move Employees to the infirmary. The phone action takes priority over the extra-coffee prop. A `completed` activity shows a checkmark over the character for 4 s from the first observation of that `state_since`, including after a following `idle`. Because the Collector can report `completed` and `idle` together, an Employee last observed as `working` or `thinking` that becomes `idle` shows the same checkmark; other transitions to `idle` and the first observation of an Employee do not. With reduced motion the checkmark is static. A `limited` Employee shows a wall clock; the visible screen of a rear-facing desk is darkened, and other placements show a small switched-off monitor beside the character. A known `reset_at` appears as "Resets" (초기화) with a time in the character label and detail. `unknown` characters are dimmed and desaturated. The `study-mode` condition adds a book stack on the desk side of the character.
- Desk positions align seated bodies with chair cushions and working hands with keyboards and mice at every viewport and zoom level; characters scale proportionally with the artwork. Furniture and characters share a depth order. Selected Employees show an outline of body portions hidden behind furniture. The infirmary has one bed with a reclining pose. Fika has three seats. Every seat is kept for the visit: a desk, Lounge seat, or bed stays with its occupant until that Employee leaves the room, so others never move when someone leaves; a newcomer takes the lowest free seat, and on first display Employees take seats in seat-number order. Desk assignments start over when the displayed Branch or floor page changes. Desk rooms show occupants beyond their desks as "+N", and the next of them takes a desk that becomes free. Facility seats remain reserved until the occupant leaves, including during coffee visits. Additional occupants stand in a first-arrival waiting line and take the next vacant seat or bed. The scene shows up to six standing Fika occupants and four standing infirmary occupants; further occupants remain in the count and team list, and selecting one reveals that Employee in a standing spot without changing queue order.
- Working Employees independently alternate three typing and three mouse gestures.
- Walking (`floor.js`, `walk.js`). The floor of `office.png` is described as furniture footprints (floor-contact polygons of desks, chairs, sofa, tables, ottoman, lamp, counter, bed, walls, posts, and door leaves, in percent of the artwork, measured on the artwork: legs, pedestals, and wheel bases, with table and desk tops projected down to the floor), the outline of the floor slab up to its cut front edge, and a graph of walkable waypoints in open aisles, the corridor, the lounge, the strip behind the sofa to the counter, and the open front edges of the Common Office and infirmary. A walker's feet are a box as wide as the widest stance of the walking frames in either facing (2.7 % of the artwork width) and as deep as the soles. Every graph connection, and every straight step that replaces corners on a route, sweeps that box without touching any footprint and keeps the feet on the slab. The floor behind the standing lamp is kept clear as well, so no walker's head passes behind the lamp shade. In front of the Common Office corner post, which stands on the slab edge, the outline reaches onto the top of the cut face so walkers can pass the post. Each seat names the waypoint on its free side (behind a rear-facing desk chair, behind the desk for a front-facing one, in front of the sofa cushion or the armchair seat, beside the bed); a walker leaves a seat through that point and sits down from it, and that step touches only the seat's own chair or sofa (and, at a desk, the desk the chair is tucked under). In the lounge the gap between the sofa and the coffee table is only wide enough in front of the left cushion, so Lounge colleagues reach the counter around the table: past its left end, between the table and the ottoman, in front of the armchair and the right cushion, between the sofa end and the armchair, past the side table, and up the right side to the strip behind the sofa. When a shown Employee's place changes on the displayed Branch (desk to Fika or infirmary and back, a newcomer taking a free desk, a waiting spot to a free seat, or a counter visit), the Employee walks the shortest route through the graph instead of sliding across the room. A walker sent elsewhere while on the step into or out of a seat first returns to that seat's free side. The first sighting, another Branch, and reduced motion place the Employee directly. Waiting spots stand on open floor, clear of furniture.
- Walking views. The sprite follows the heading of the current stretch: heading down the screen (toward the viewer) shows the front standing frame of the employees atlas, heading up the screen shows the rear coffee-standing frame; each is mirrored for leftward or rightward walks, and level stretches keep the last view. A step cue needs no extra art: the figure bobs slightly twice per cycle while the weight-bearing leg is held on the floor, so the feet lift in turn. A drink being carried back from the counter stays in the hands of the rear view; the front frames hold their own items or keep their hands in their pockets, so no extra drink is drawn there.
- Depth while moving. Furniture layers redraw the furniture pixels of `office.png` over actors; each layer is tied to its footprint. A walker's stacking order is recomputed every frame from its feet: in front of layers whose footprint lies behind the feet, behind layers whose footprint lies in front; beside a piece whose pixels the walking sprite overlaps, the nearest end of its footprint decides. Lounge walls and the counter hide walkers in the aisle behind them, the sofa hides the lower body of a walker on the strip behind it, the lamp stool, coffee table, ottoman, armchair, and side table cover a walker passing behind them, and seated occupants stay in front.
- Cheese and Pepper walk, sit, groom, and nap along the corridor and lounge part of the same graph (the corridor, the lounge front strip, the way around the coffee table, and the right side of the lounge), so their paws keep off furniture and they share the depth rule. Their walk is a gait cycle driven by distance walked: diagonal leg pairs alternate through lift, swing, plant, and push; the body bobs and the head nods twice per cycle; the tail sways a quarter cycle behind. A still copy of the cat stays under the moving parts near the hips and tail base, so part edges never show the floor as thin seams at any zoom. One cycle moves the cat by a fixed stride and speed equals stride divided by each cat's own cycle period, so paws do not slide. Cats slow down before waypoints and turn by a short flip with a slight tilt on slopes. Starting from a rest the cat stands up first and eases into the walk; stopping, it slows, lowers its hindquarters, and sits; a nap follows a short sit.
- Fika Employees occasionally walk to the coffee counter, wait while the drink is prepared ("Brewing" for coffee, "Steeping" for tea, "Pouring" otherwise), take a drink, and walk back to their seat. Visits affect presentation only and stop when the Employee leaves Fika. Only one Employee uses the counter at a time.
- Lounge activities (`lounge.js`). Each seated Lounge colleague has a profile seeded from its `agent_id`, stable for the visit: a drink (coffee, tea, juice, water, soda, or milk; coffee and tea use the ten mug designs, the others have their own glass or can), a sip rhythm (interval, duration, and style: raised to the mouth, held up briefly, or stirred), and a page-turn interval. Sip timing is scheduled per colleague, so colleagues never sip in step. Colleagues rotate between drinking, reading (an open book held in both hands with a page that turns; on the rear-facing chair the book is raised beside the head, showing its covers, spine, and page edges behind the reader's hands), and sitting. When two or more colleagues are seated, a pair occasionally talks: both turn their heads toward each other and small speech bubbles alternate between them for a few seconds, each showing one non-verbal pixel glyph (dots, heart, cup, light bulb, question mark, note, or sun); bubbles never contain words or agent data. Pairs vary, usually nearest neighbours. A counter visit can change the drink. Lounge activities are presentation only.
- Window lighting follows the displayed Branch's local time: morning from 05:00, day from 10:00, evening from 17:00, and night from 20:00. Night windows show a moon and stars while indoor lamps remain warm. When the Branch `time` is a valid IANA time zone, the heading clock, date, window lighting, and usage-limit reset times use that zone and the clock is labeled with the zone; a missing or fictional value falls back to browser-local time labeled "Browser time" (브라우저 시각). The scene caption names the current light period (Morning, Day, Evening, Night).
- Search, status filters, and room filters select the team list and highlight matching characters. Status filter chips wrap onto a second line on narrow screens instead of scrolling sideways. Selecting a Colleague opens their current details. Selection survives Project-page changes while the Employee still matches the filters. Remote participants of local Projects remain visible in shared facilities on every Project page.
- Dashboard and Colleagues provide tabular views. Workload is shown as the reported count of recent tool executions ("N recent tools"); the window size is not displayed because it is not part of the payload. Projects and Branches link to the office; Timeline and Work log are described in Sections 6.5 and 6.6.
- Dashboard cards: Branches, On duty, Waiting, Error, "Waited today" (대기 시간 합계: the sum of `seconds.waiting` of the work log of the browser-local day, which HQ clips to now, with the number of waits; refreshed every 60 s and when the Dashboard opens; the request names the whole day, so pages share HQ's answer (Section 4.2); hidden while replaying), and "Longest current wait" (현재 최장 대기: the longest time since `state_since` among on-duty Employees in `waiting`, with that Employee's name, at the shown time).
- The "Recent activity" card of the office lists changes observed since the page loaded; while replaying it lists the recorded changes of the shown day up to the replay time.
- Display settings control language, name labels, reduced motion, automatic or manually selected window light, and browser notifications (Section 6.4). The interface also respects the system reduced-motion preference. Hidden views and reduced motion pause random office activity. With reduced motion nobody walks, cats keep a static pose, and each Lounge colleague shows a static prop, a cup or a book, without sips, page turns, or speech bubbles.
- Decoration (`decor.js`). Code-drawn paintings are placed inside the five framed pictures of `office.png`: each painting is a small pixel grid (landscapes, sea, mountains, botanical, still life, and abstract compositions in the office palette, with slight per-cell tone changes) mapped onto the frame's measured quadrilateral on the isometric wall and clipped to it. A few code-drawn flower props (vases, jars, bowls, and pots with blossoms in several colours) stand on free surfaces: the lounge coffee table, the top of the lounge refrigerator, the cabinet in the left project room, the infirmary window sill, and the Common Office desk corner; none is a seat or on a floor route, and each has its own stacking depth. Paintings and flowers are chosen deterministically from the Branch id, so each Branch looks distinct but stable; frames in one office never repeat a painting. They contain no text, logos, or Branch data and follow the room light.
- The browser marks activity unverified when its HQ connection is lost or the Branch is unreachable. Tables mark on-duty, off-duty, and on-leave rows of such Branches alike. Placement, pose, and counts keep the last observed state, dimmed and marked with "?".
- The wording names the cause. While the page has no HQ connection, the Branch status chip, the Branch footer, the Branches view, the unverified tooltip, and the detail note say "Not connected to HQ" (HQ 연결 끊김). While the page is connected but HQ reports the Branch unreachable, the same places say "Waiting for Branch report" (지점 보고 대기); this covers the window after an HQ restart, when the page reconnects within seconds but each Collector reports again only on its next retry (up to 60 s). The footer keeps the age of the last report in both cases.

### 6.3 Synthetic demonstration mode

The `/?demo=1` URL loads fictional Employees from `demo.js` and displays a Demo label. The fictional roster includes three Lounge colleagues, so Lounge activities and counter visits are visible. It does not open a live socket, write to HQ, or send browser notifications. Display settings switch between Demo and live views.

`demo.js` also generates three days of history ending at page load: shifts with rests of 1 to 13 hours and activity drawn from a fixed mix, from a random generator seeded by each `agent_id`, so the same structure appears on every load; the Home Branch stops reporting for 36 minutes a day earlier and the Night Branch 14 minutes before load. The Timeline, replay, Work log, and waiting times read this history through the same calls as live data, computed in the page with the rules of Sections 4.4 and 4.5.

Closed Branches and Projects retain their cards, office access, history, and a Closed badge. A previously observed Project remains listed when no Employee remains in a snapshot. Close record opens a keyboard-accessible password dialog. The token is cleared before submission and sent only in the closure request's Authorization header; it is never put in a URL, browser storage, DOM text, or logs. Replay, demo, and disconnected views disable closure. [Installation](install.md#68-close-a-branch-or-project) describes administrator setup.

### 6.4 Browser notifications

The page raises notifications through the Web Notification API (`notify.js`). A browser notification exists only while a page with the setting turned on is open. HQ sends the same notifications to an ntfy topic when configured (Section 4.6).

- Setting: "Browser notifications" (브라우저 알림) in display settings, off by default. Turning it on requests the browser permission from that click. The choice is kept in local storage (`agentville-notifications`) when available. The setting shows its state: On (켜짐), Off (꺼짐), blocked by the browser, or not supported. A page that is not a secure context (plain HTTP other than localhost) cannot use notifications; the control is disabled with a note that HTTPS or localhost is required. Demo mode disables the control and never notifies.
- Triggers, only for transitions the page observes:
  - an Employee enters `waiting` or `error` (a new `state_since` in the same state counts as a new entry);
  - a Branch becomes unreachable (`reachable` true to false) or reachable again;
  - a known Branch or Project has a higher `reopen_count`, including from an accepted Collector snapshot.
- Not notified: `limited`, `completed`, idle progression, Contractors, unverified marks, the first state after load, the first state after a reconnect (resync), and the first state of a newly appearing Employee or Branch. While replaying (Section 6.5) live states are recorded as a baseline and nothing is notified; changes that happened during the replay are not notified afterwards.
- Reopening alerts use the title "Branch {alias} reopened" or "Project {alias} reopened". Branch and Project counters have separate notification subjects and follow the same opt-in, baseline, replay, and rate-limit rules.
- Content is text only, in the interface language at the time of sending. Employee: title "{name} is waiting" / "{name} has an error" ("{name} 대기" / "{name} 오류"), body provider initials, Project alias, and Branch alias ("CL · alpha · Home"). Branch: "{alias} is unreachable" / "{alias} is reporting again" with a fixed explanatory body. Notifications never include tool names, tool arguments, prompts, paths, or account details. The icon is `favicon.svg`. Each Employee and each Branch has its own `tag`, so a newer notification replaces an older one for the same subject.
- Rate limit: at most one notification per subject per 30 s. A change inside that window is held until the window ends and is sent only if the subject is still in that state and it differs from what was last notified. When more than three subjects qualify in one update, a single summary is sent instead: "{n} colleagues need attention" (동료 {n}명 확인 필요), or "{n} colleagues and branches need attention" (동료·지점 {n}건 확인 필요) when Branches are included.
- Click: focuses the window, clears search and filters, opens the virtual office of the Employee's Branch with that Employee selected (a summary selects its first Employee), or the Branches view for a Branch notification, then closes the notification. A Project reopening opens the Projects view.
- A missing or throwing `Notification`, a refused permission, or unavailable local storage leaves the rest of the page unaffected.

### 6.5 Timeline and Replay

- The Timeline lists the recorded changes of one day (`GET /api/v1/changes` for that day, clipped to the kept history and now), newest first: activity and presence transitions with the Employee name, Project, and Branch, and Branch reachability ("is unreachable", "is reporting again"). Times and day boundaries use the displayed Branch's time zone rules (Section 6.2). The list shows at most 400 entries in its own scroll area and notes when more exist. Today's list is reloaded at most every 15 s while the view is rendered; the request names the whole day, which HQ clips to now, so reloads and pages share HQ's answer for up to 30 s (Section 4.2).
- Replay control (되감기): a day picker limited to the kept history, a time slider over that day (from its start or the start of history to its end or now), play and pause, speeds 1x, 10x, and 60x, and steps to the previous and next listed change. Selecting a list entry, moving the slider, or pressing play starts replay; Escape or "Back to live" ends it.
- While replaying, every view shows `GET /api/v1/state?at=` instead of the live state: the office, its people and walks, team list, details, tables, Branch indicators, clock, window light, and idle progression all use the replay time. A banner above the heading on every view reads "Replay <date time>" (되감기 <날짜 시각>) with the step, play, and speed controls and "Back to live" (실시간으로 돌아가기); the office scene is outlined.
- Fetching: a chosen time (slider, entry, step) is read exactly, after 150 ms without further movement; playback reads one state per replayed minute, at its last instant, so it asks HQ at most once per replayed minute at any speed. Responses are cached (360 entries). Playback stops at now; crossing midnight moves the Timeline to the next day.
- A replayed state is shown as verified unless its Branch was unreachable at that time (Section 4.4).
- The live socket keeps running during replay. Its states are kept but not drawn; "Back to live" draws the latest one.

### 6.6 Work Log View

- "Work log" (근무 일지) shows `GET /api/v1/worklog` for one day: a Branch selector ("All branches" or one Branch) and a day picker with previous and next day. Days follow the selected Branch's time zone rules (Section 6.2); for all Branches, browser time. The zone is named under the controls.
- Rows are grouped Branch, Project, colleague; Branch and Project rows carry subtotals and a final row the total. Columns: On duty, the activity states, Unobserved, Waits (entries into `waiting`), Longest wait, Errors, and Limits (entries). Thinking, Closed, Limited, Not measured, and Unobserved columns appear only when a row has time in them. Durations are `h:mm`; zero is "-". The colleague column stays in place while the table scrolls sideways.
- A day before the kept history shows that no history is kept; a day that starts before it notes the time history starts. Today's log is reloaded every 60 s while shown. The search field filters rows by name, Project, and Branch.

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

Release work records: [0.3.0](milestone-0.3.0.md) and [0.4.0](milestone-0.4.0.md). Their M identifiers are local to each document.

## 9. Open Items

### 9.1 Planned, not implemented

- Fork or mirror grouping, and Project `alias`, in Branch configuration (Section 1.3).
- History of account and model changes per Employee (Section 1.4). The `account.changed` observation is defined but not emitted.
- Monitor count by workload, and a per-Branch workload window and mapping (Section 2.5). The window is fixed at 5 minutes.
- Precomputed daily totals: each work log request is computed from the recorded changes (Section 4.5).
- Contractors in the work log, and a Branch filter in the Timeline.

### 9.2 Open questions

- `fast_mode` signal: no Adapter reports it yet, so the default `extra-coffee` rule does not match observed data (Section 1.6).
- Default values: process scan interval, heartbeat interval.
- Claude Code: meaning of `state: blocked` and `status: shell`.
- Codex: live observation of `waitingOnApproval`, `waitingOnUserInput`, and `systemError`.
- Antigravity waiting and usage-limit signals.
- Switching the login within one Claude home: not yet in use; decided when adopted. Accounts in separate homes are configured per home.
- Presence `retired` (거두어짐): a colleague whose model was withdrawn and cannot return. No signal identifies it yet; until then such a colleague passes to `on_leave`.
- Contractor grouping when counts are large (Codex subagent threads dominate recent history).
- English terms pending confirmation: on duty, off duty, on leave, shift, seat, unreachable, closed.
