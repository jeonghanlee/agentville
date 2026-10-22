# AgentVille

A self-hosted, read-only virtual office for AI coding agents. Each host runs a Collector that observes local Claude Code and Codex sessions; one host runs HQ, which stores current state and serves the office view to a browser.

AgentVille observes only. It never starts, resumes, answers, or interrupts an agent, and never modifies agent configuration.

## Architecture

````text
Branch (any host)                                  HQ (one host)
┌──────────────────────────────────────┐          ┌───────────────────────────────┐
│ ~/.claude/sessions, transcripts      │          │ POST /api/v1/ingest/messages  │
│ Codex app-server socket, rollouts    │          │ SQLite (WAL), current state   │
│        │                             │  HTTPS   │ GET  /api/v1/state, ...       │
│ Adapters → Judge → Sender ───────────┼─────────▶│ WS   /ws/v1/live ─────────────┼──▶ Browser
│        │                             │ outbound │ /  static Web UI              │
│ state: seq, roster.json              │  only    └───────────────────────────────┘
└──────────────────────────────────────┘
````

| Component | Role |
|---|---|
| Adapter | Reads one provider's local sources and turns them into observations. |
| Judge | Assigns observations to colleagues and decides presence and activity. All state decisions are made on the Branch. |
| Sender | Delivers protocol messages to HQ; outbound only, no queuing across outages. |
| HQ | Validates, stores, and serves the current state of every Branch. |
| Web UI | Static page served by HQ; live updates over WebSocket. |

Guides: [docs/install.md](docs/install.md) (installation). Specifications: [docs/architecture.md](docs/architecture.md) (domain, state model, sources, HQ, Web UI), [docs/protocol.md](docs/protocol.md) (Branch–HQ messages, data minimization), [docs/fixtures.md](docs/fixtures.md) (synthetic test data).

## Terms

| Term | 한국어 | Meaning |
|---|---|---|
| Branch | 지점 | A host running a Collector. |
| HQ | 본사 | The host running the hub; also a Branch. |
| Room | 방 | One repository (Project). |
| Common Office | 공용 사무실 | Agents working outside any repository. |
| Lounge (Fika) | 휴게실 | Colleagues idle for an hour or more. |
| Infirmary | 양호실 | Colleagues in `error`. |
| Colleague | 동료 | A persistent agent identity: project, host, provider, seat. |
| Contractor | 외주 | A subagent working for a colleague. |
| Seat | 자리 | A colleague's position within a room. |
| On duty / Off duty / On leave | 출근 / 퇴근 / 휴가 | Presence; on leave after 7 days off duty. |
| Working, Thinking, Waiting, Idle | 작업 중, 생각 중, 대기, 유휴 | Activity states. |
| Closed | 닫힘 | A turn ended (`completed`). |
| Error | 오류 | Agent-level failure. |
| Limited | 한도 | Provider usage limit reached. |
| Not measured | 재지 못함 | State could not be determined (`unknown`). |
| Unreachable | 연락 끊김 | No message from a Branch within three heartbeat intervals. |

## Install

Supported: Linux with Python 3.12 or later, for example Debian 13, Ubuntu 24.04 (Debian family), and Rocky Linux 9 and 10. The [Installation Guide](docs/install.md) covers requirements, download, install, services, connecting other hosts, upgrade, and removal. In short, from a clone, on the HQ host:

````bash
python3 -m venv ~/.local/opt/agentville
~/.local/opt/agentville/bin/pip install '.[hq]'      # Branch only: pip install .
mkdir -p ~/.local/bin
ln -sf ~/.local/opt/agentville/bin/agentville-collector ~/.local/bin/
ln -sf ~/.local/opt/agentville/bin/agentville-hq ~/.local/bin/       # HQ host
````

`~/.local/bin` must be on `PATH`.

## Run on one host

In the foreground:

````bash
agentville-hq                 # agentville-hq: serving http://127.0.0.1:8470/ (database …)
agentville-collector          # agentville-collector: Branch <alias> (<host.id>) reporting to http://127.0.0.1:8470
````

Open `http://127.0.0.1:8470/`. `/?demo=1` shows synthetic data without connecting to HQ.

As systemd user services, see [Installation Guide, Section 4](docs/install.md#4-start-the-services).

## Collector configuration

The first start writes `~/.config/agentville/config.yaml` (mode 0600). It is a local file and is never committed or sent as a whole.

````yaml
host:
  id: <generated uuid>          # never change
  alias: <hostname>             # Branch name shown in the office
  country: ""
  time: Asia/Seoul              # IANA zone; drives the Branch clock and window light
  location: ""
hq:
  url: http://127.0.0.1:8470
  # token: <branch token>       # required when HQ is on another host
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
  - {provider: "*", effort: xhigh, condition: study-mode}
  - {provider: "*", effort: low, condition: light}
collector: {poll_interval: 1.0, heartbeat_interval: 30}
````

- `time` defaults to the host's local time zone at first start. A value that is not a valid IANA zone is shown as a label; the Web UI then uses browser time for the clock and window light.
- One provider home is one account. `~/.claude` is always listed; the other homes (`~/.claude-*`, `~/.codex`, `~/.codex-*`) are those found at first start. Each provider's homes are numbered `<provider>-account-1`, `-2`, …; rename or add them here.
- Condition rules are evaluated in order and the first match wins; unmatched combinations are `normal`. The `extra-coffee` rule needs a fast-mode signal, which no Adapter reports yet.
- Thresholds are seconds of idleness for phone, dozing, and lounge, and of absence for leave.
- Values are checked at start. A file holding `hq.token` must not be readable by group or others.
- State files: `~/.local/state/agentville/seq` and `roster.json` (colleague identities across restarts).
- `agentville-collector --output -` prints messages as JSONL instead of sending them. It reads the state files but never writes them.

## Several hosts

HQ binds to loopback by default. To add Branches on other hosts, HQ gets a token file (one token per Branch `host.id`) and a viewer token, and is served over HTTPS, either directly (`--tls-cert`, `--tls-key`) or behind a reverse proxy. Each Branch sets `hq.url` to the HTTPS address and `hq.token` to its token. Branches connect outbound only; HQ never connects to a Branch. The steps are in [Installation Guide, Section 6](docs/install.md#6-connect-a-branch-on-another-host).

## Security and data

- HQ on loopback accepts Branches on the same host without a token, unless their `host.id` is listed in the token file or `--no-trust-loopback` is set. It rejects foreign `Host` headers, cross-site WebSocket origins, and ingest requests from browsers.
- Sent to HQ:
  - Branch: alias, country, time zone, location, thresholds.
  - Colleague: id, display alias (currently always null), project id and alias, provider, seat, presence and its time, `account_alias`, model, settings (such as effort), condition, and, while on duty, the instance id, start time, and runtime (type `tmux`, `shell`, or `app_server`; for tmux, the pane location reported by Claude Code).
  - Activity: session id, state and its start time, source, confidence, tool name, usage-limit reset time (`reset_at`), and workload (tool executions in the last 5 minutes).
  - Contractor: id, parent instance id, provider, origin, status, state and its start time, tool name.
  - For a repository without a remote, the project alias is the repository directory's base name and `project_id` is a hash of the host id and repository path; the path itself is not sent.
- Never sent to HQ: tool arguments, prompts, file paths, local paths of repositories without a remote, account details beyond `account_alias`, command lines, environment variables, details of waiting requests and errors, provider subagent ids.
- HQ keeps received messages for 30 days (`--retention-days`) and the current state of each Branch.

## Web UI

- Views: Virtual office, Dashboard, Colleagues, Projects, Timeline, Branches.
- Settings: name labels, reduced motion, window light, language (English / 한국어), browser notifications for waiting, error, and Branch reachability.
- When HQ or a Branch is not reporting, the last observed state stays in place, dimmed and marked unverified.

## Development

````bash
python3 -m venv .venv && .venv/bin/pip install -e '.[hq,test]'
.venv/bin/python -m pytest -q
````

Test data is synthetic, produced by `tests/fixtures/*/generate.py`; real logs are never committed.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE); artwork provenance in [docs/design/artwork.md](docs/design/artwork.md).
