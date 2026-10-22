# Configuration

## Scope

This document covers the Collector configuration file on each host.

**Out of scope:** HQ command-line options and token files ([Installation](install.md) Section 6).

Each host that runs a Collector has one local configuration file.


The first start writes `~/.config/agentville/config.yaml` (mode 0600). It is a local file and is never committed or sent as a whole.

```yaml
host:
  id: <generated uuid>          # never change
  alias: <hostname>             # Branch name shown in the office
  country: ""
  time: Asia/Seoul              # IANA zone; drives the Branch clock and window light
  location: ""
hq:
  url: http://127.0.0.1:8470
  token: <branch token>         # added by hand; required when HQ is on another host
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
aliases:
  3f2c9a7e-1b4d-4c8e-9a51-6d0e2b7f4c10: Reviewer   # colleague id: display name
```

- `time` defaults to the host's local time zone at first start. A value that is not a valid IANA zone is shown as a label; the Web UI then uses browser time for the clock and window light.
- One provider home is one account. `~/.claude` is always listed; the other homes (`~/.claude-*`, `~/.codex`, `~/.codex-*`) are those found at first start. Each provider's homes are numbered `<provider>-account-1`, `-2`, ...; rename or add them here. A provider with no home found is written as `codex: []`; to add one, replace `[]` with a list as in the example.
- The generated file writes provider homes as absolute paths with the home directory expanded (e.g. `/home/<user>/.codex`). A `~` is accepted when editing, as in the example above.
- Condition rules are evaluated in order and the first match wins; unmatched combinations are `normal`. The `extra-coffee` rule needs a fast-mode signal, which no Adapter reports yet.
- `aliases` gives colleagues display names. The key is the colleague id, shown in small text in the Colleague detail of the office page; the value is a name of at most 40 characters. A colleague without an alias is shown as provider and seat, for example "Codex 2"; seat numbers are unique per provider on a Branch. The generated file contains `aliases: {}`.
- Thresholds are seconds of idleness for phone, dozing, and lounge, and of absence for leave.
- `collector.poll_interval` is the seconds between polls of the agent sources and must be greater than 0. `collector.heartbeat_interval` is the seconds between heartbeats to HQ, at least 1; HQ receives it with each heartbeat.
- Values are checked at start. `host`, `hq`, `thresholds`, `providers`, `collector`, and `aliases` must be mappings, each `providers` entry a list of homes, and `conditions` a list of rules; thresholds are integers with phone <= doze <= lounge. A file that is not valid YAML or holds a wrong value stops the Collector with one line, for example `agentville-collector: invalid configuration: thresholds must be a mapping`. A file holding `hq.token` must not be readable by group or others.
- State files: `~/.local/state/agentville/seq` and `roster.json` (colleague identities across restarts). An unreadable `roster.json` is reported on standard error, the roster starts empty, and the file is kept as `roster.json.bad` when the new roster is written.
- `agentville-collector --output -` prints messages as JSONL instead of sending them. It reads the state files but never writes them.

After editing, restart the Collector: `systemctl --user restart agentville-collector`.
