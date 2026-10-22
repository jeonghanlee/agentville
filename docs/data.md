# Data and Security

## Scope

This document covers what the Collector sends to HQ, what it never sends, and how HQ protects access.

**Out of scope:** host hardening, TLS certificate management, and backup.

AgentVille sends only state, never content. The lists below are exact.

- HQ on loopback accepts Branches on the same host without a token, unless their `host.id` is listed in the token file or `--no-trust-loopback` is set. It rejects foreign `Host` headers, cross-site WebSocket origins, and ingest requests from browsers.
- The page sends the viewer token as the first message on the live WebSocket, never in a URL, so it does not appear in proxy access logs. HQ sends no state before it and closes the socket with code 4401 when it is missing, wrong, or not received within 5 s.
- Sent to HQ:
  - Every message: `schema_version`, `branch_id` (the Branch `host.id`), `seq` (per-Branch sequence number), `kind` (`snapshot`, `heartbeat`, `branch`, `agent`, `activity`, or `contractor`), `event_at`, `sent_at`, and `payload` (the fields below).
  - Heartbeat: the heartbeat interval in seconds (`collector.heartbeat_interval`).
  - Branch: alias, country, time zone, location, thresholds.
  - Colleague: id, display alias (set in the Collector configuration `aliases`, otherwise null), project id and alias, provider, seat, presence and its time, `account_alias`, model, settings (such as effort), condition, and, while on duty, the instance id, start time, and runtime (type `tmux`, `shell`, `app_server`, or `rollout`; for tmux, the pane location reported by Claude Code).
  - Activity: colleague id, instance id, session id, state and its start time, source, confidence, tool name, usage-limit reset time (`reset_at`), and workload (tool executions in the last 5 minutes).
  - Contractor: id, parent instance id, provider, origin, status, state and its start time, tool name.
  - For a repository without a remote, the project alias is the repository directory's base name and `project_id` is a hash of the host id and repository path; the path itself is not sent.
- Never sent to HQ: tool arguments, prompts, file paths, local paths of repositories without a remote, account details beyond `account_alias`, command lines, environment variables, details of waiting requests, errors, and usage limits (only the reset time is sent), provider subagent ids.
- HQ keeps received messages for 30 days (`--retention-days`) and the current state of each Branch.
