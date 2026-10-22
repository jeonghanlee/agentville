# Changelog

## Scope

This document lists the user-visible changes of each AgentVille release.

**Out of scope:** internal refactoring and test-only changes.

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
