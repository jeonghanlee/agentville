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
- One process lifetime is one shift of an Employee.
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

## 3. Open Items

- Default values for workload window and monitor mapping (after M0).
- English terms pending confirmation: on duty, off duty, on leave, shift, seat, unreachable, closed.
