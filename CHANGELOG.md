# Changelog

## Scope

This document lists the user-visible changes of each AgentVille release.

**Out of scope:** internal refactoring and test-only changes.

## 0.4.0 - Unreleased

### Web UI

- One enlarged office contains 20 desks in four Project areas of 4, 4, 4, and 8 places, two six-chair meeting rooms, and 28 Fika places at two tables, two sofas, and three high tables. Project navigation pages by four. Colleagues take their Project's desks first, then vacancies shared with other Projects and Common Office; Fika colleagues sit before joining a waiting line. The infirmary is removed: colleagues in error stay at their desks.
- Same-Project colleagues meet after 60 seconds of observed concurrent work, with up to two meetings of different Projects per Branch. Participants retain identity, selection, and held desks; meetings follow immediate exits or a 30-second grace period, survive reconnects, and are excluded from replay.
- Walking, furniture occlusion, seated poses, gestures, lighting, and decoration follow the office artwork. Colleagues seated with their backs to the viewer rest their feet under the table, and their Contractors stand on the free side of the chair. The full-seat and meeting demonstrations expose all 60 seat ids.

## 0.3.0 - Observation Release - 2026-10-22

**Observation Release**

### Collector

- Child agent CLIs are Contractors of the nearest observed parent, including descendants launched through a shell. If the parent is discovered later, the former independent colleague goes off duty while retaining its ID and history; current activity continues as a Contractor.
- Codex process matching falls back to an unambiguous process-start match when file descriptors cannot be read. Completed rollout files do not create on-duty colleagues after a Collector restart until they are written again.
- Antigravity CLI (`agy`) presence and observable activity are supported through held presence locks and transcripts. Enable `providers.antigravity` in existing configurations; new configurations discover Gemini homes only when they contain `antigravity-cli`.
- Antigravity reports working, completion, idle, error, and unknown activity. Completed tools clear correctly, and replayed transcript records do not increase workload or restore old activity after rotation or truncation.

### HQ

- Conflicting message content with the same Branch ID and sequence number produces a shared-identity warning. Identical retries remain duplicates without a warning.

### Web UI

- Antigravity colleagues and Contractors show the `AG` provider label.
- Branches with the same alias include their full IDs in colleague details, selectors, and work-log headings.

### Documentation and deployment

- Remote Collector procedures cover SSH tunnels, Docker host and bridge networking, persistent config and state, volume ownership, and manual restart.
- Configuration documents distinguish Antigravity homes from Gemini CLI homes and describe the supported activity signals.

**Full Changelog**: https://github.com/jeonghanlee/agentville/compare/0.2.0...0.3.0

## 0.2.0 - 2026-10-22

### Collector

- `aliases` in the configuration gives colleagues display names (colleague id to name, at most 40 characters, in the configuration of the colleague's Branch); the name is sent as the colleague `alias`.
- Seat numbers are unique per provider on a Branch, so default names such as "Codex 2" no longer repeat across repositories. Rosters with duplicate seats are renumbered at start.

### HQ

- State history: every change to current state is recorded with the time of the fact (never later than its receipt by HQ) and kept for `--retention-days` (default 30); older changes fold into a baseline. A 0.1.0 database starts its history at the first start of 0.2.0.
- New read endpoints: `/api/v1/state?at=`, `/api/v1/history`, `/api/v1/changes`, `/api/v1/worklog`. History reads use their own read-only database connections and hourly state checkpoints, so their cost follows the requested period and they do not delay ingest or live updates; identical `changes` and `worklog` requests within 30 s share one answer.
- Errors about the token, viewer token, and notification files read `agentville-hq: <file>: <reason>`, e.g. `agentville-hq: /etc/agentville/tokens.yaml: No such file or directory`.
- External notifications to an ntfy topic with `--notify-config`, following the browser notification rules; off by default.

### Web UI

- Work log view: time per state for one day, grouped by Branch and Project, with waits, longest wait, errors, limits, and unobserved time.
- Timeline lists the recorded changes of a chosen day and replays the office at 1x, 10x, or 60x, with steps between changes and "Back to live".
- Dashboard cards "Waited today" and "Longest current wait"; Colleague detail shows waiting time today and the colleague id.
- Colleague aliases are shown wherever the default name was.
- Demo mode includes synthetic history for the Work log and replay.

## 0.1.0 - 2026-10-22

First release.

### Collector

- Observes Claude Code sessions and transcripts, and Codex through the app-server WebSocket and rollout files.
- Codex runs outside the app-server daemon (for example `codex exec`) are observed from rollout files with low confidence; they go off duty 30 minutes after the last rollout write.
- States: Working, Waiting, Idle (desk, phone, dozing, Lounge), Closed, Error, Limited, Not measured. Presence: on duty, off duty, on leave.
- Contractors (subagents) reported with their parent colleague.
- Seats and the colleague roster persist across restarts; workload counts tools started in the last 5 minutes.
- Usage limits: Claude `quotaLimits` and Codex `usage_limit_exceeded` report Limited with the reset time.
- One numbered account per provider home (`<provider>-account-N`).
- `--once`, `--output` (read-only diagnostics), `--version`.

### HQ

- FastAPI service with SQLite (WAL); messages kept 30 days (`--retention-days`), current Branch state kept regardless.
- Branch tokens (at least 16 characters) and a viewer token sent as the first WebSocket message.
- Host and Origin checks; ingest rejects browser requests; batches over 1000 messages are rejected with HTTP 413.
- HTTPS directly (`--tls-cert`, `--tls-key`) or behind a reverse proxy (`--no-trust-loopback`, `--server-name`).
- `--version`.

### Web UI

- Isometric office per Branch: Project rooms, Common Office, Lounge, Infirmary; Branch-local clock and window light.
- Dashboard, Colleagues, Projects, Timeline, and Branches views.
- English and Korean.
- Unverified display for Branches that stop reporting; "Waiting for Branch report" after an HQ restart.
- Opt-in browser notifications.
- Demo mode (`/?demo=1`).

### Documentation and deployment

- User manual (mdBook) published to GitHub Pages: installation, configuration, using the office, data and security.
- systemd user units for HQ and the Collector; `install.sh` installs or upgrades in one command.
- Supported: Linux with Python 3.12 or later (Debian 13, Ubuntu 24.04, Rocky Linux 9/10).
