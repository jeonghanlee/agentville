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

Specifications: [docs/architecture.md](docs/architecture.md) (domain, state model, sources, HQ, Web UI), [docs/protocol.md](docs/protocol.md) (Branch–HQ messages, data minimization), [docs/fixtures.md](docs/fixtures.md) (synthetic test data).

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

## Requirements

- Linux with Python 3.12 or later.
- Claude Code and/or Codex CLI on the observed hosts. Codex live state requires its shared app-server daemon.

## Install

From a clone, on every host:

````bash
pipx install '.[hq]'        # HQ host and Branches; '.' alone is enough for a Branch only
````

`agentville-hq` and `agentville-collector` are installed in `~/.local/bin`. A virtual environment works as well (`python3 -m venv ... && pip install '.[hq]'`); adjust `ExecStart` in the service units to its `bin` directory.

## Run on one host

````bash
agentville-hq                 # http://127.0.0.1:8470
agentville-collector          # reports to http://127.0.0.1:8470
````

Open `http://127.0.0.1:8470/`. `/?demo=1` shows synthetic data without connecting to HQ.

As systemd user services:

````bash
install -Dm644 deploy/systemd/agentville-hq.service        ~/.config/systemd/user/agentville-hq.service
install -Dm644 deploy/systemd/agentville-collector.service ~/.config/systemd/user/agentville-collector.service
systemctl --user daemon-reload
systemctl --user enable --now agentville-hq agentville-collector
````

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
  - {provider: "*", effort: low, condition: light}
collector: {poll_interval: 1.0, heartbeat_interval: 30}
````

- One provider home is one account. Homes found at first start (`~/.<provider>`, `~/.<provider>-*`) are numbered `<provider>-account-1`, `-2`, …; rename or add them here.
- Thresholds are seconds of idleness for phone, dozing, and lounge, and of absence for leave.
- Values are checked at start. A file holding `hq.token` must not be readable by group or others.
- State files: `~/.local/state/agentville/seq` and `roster.json` (colleague identities across restarts).
- `agentville-collector --output -` prints messages as JSONL instead of sending them.

## Several hosts

HQ binds to loopback by default. For Branches on other hosts:

1. Create a token file on HQ, mode 0600, one token of at least 16 characters per Branch:

   ````yaml
   # ~/.config/agentville/tokens.yaml
   3f1c...-branch-host-id: <random token>
   ````

2. Create a viewer token file (mode 0600) for browsers.
3. Expose HQ over HTTPS, either directly or behind a reverse proxy:
   - Direct: `agentville-hq --host 0.0.0.0 --allow-remote --tokens tokens.yaml --viewer-token-file viewer.token`
   - Reverse proxy on the same host: keep `--host 127.0.0.1` and add `--no-trust-loopback --tokens tokens.yaml --viewer-token-file viewer.token --server-name hq.example.org`
4. On each Branch set `hq.url: https://hq.example.org` and `hq.token`. The Collector refuses to send a token over plain HTTP to a non-loopback HQ and does not follow redirects.
5. Open `https://hq.example.org/#token=<viewer token>`. The page moves the token to session storage and removes it from the address bar.

Branches connect outbound only; HQ never connects to a Branch.

## Security and data

- HQ on loopback accepts Branches on the same host without a token. It rejects foreign `Host` headers, cross-site WebSocket origins, and ingest requests from browsers.
- Never sent to HQ: tool arguments, prompts, file paths, local paths of repositories without a remote (hash only), account details beyond `account_alias`, command lines, environment variables, details of waiting requests and errors.
- Sent: colleague identity, project id and alias, provider, seat, presence, activity state with times, tool name, workload count, model, effort-type settings, condition, Branch alias, country, time zone, location.
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
