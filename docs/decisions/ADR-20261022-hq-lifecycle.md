# ADR: HQ-owned Branch and Project lifecycle

Date: 2026-10-22
Status: accepted
Source Session: `work/review_sessions/20261023_004636_lifecycle`
Source Decisions: D003, D004

## Scope

This decision defines record closure, automatic reopening, historical persistence, and administrator access at HQ. Collector observation rules, process control, and office layout are out of scope.

## Context

Collector snapshots replace observed Branch state. A closure record must survive that replacement and must not alter measured work. Project identity is global across Branches. Viewer access and Branch ingest credentials do not grant authority to close records.

## Decision

HQ owns a persistent lifecycle catalog independently of Collector payloads. Branch records use their Branch identity; Projects use one global Project identity with known Branch membership. Existing records start open. Closing a Branch leaves Project lifecycle and observed Employees unchanged. Closure of a known target is idempotent; unknown targets are rejected.

A newly accepted on-duty agent report, activity for its current on-duty instance, or snapshot containing an on-duty agent reopens the corresponding Branch and Project. Idle qualifies. Qualification follows HQ receipt/transaction order after closure, independent of event_at and sent_at age. Heartbeat, metadata, off-duty, duplicate, stale, and rejected messages do not qualify. Unchanged idle Collector polls therefore retain closure.

The SQLite lifecycles table holds current records; changes, baseline, and checkpoints preserve their history under the existing retention rule. Branch records use a branch-prefixed identity. Projects use an empty storage branch and a project-prefixed identity, retaining Branch membership for filtered history. Lifecycle changes use HQ time in transaction order; activity timestamps and work-log measurements retain their existing meaning. State and WebSocket responses expose lifecycle; Collector wire schema version 1 is unchanged.

Closure requires a distinct administrator bearer token loaded from a private file at startup. The token is ASCII, at least 16 characters, without whitespace, and differs from all viewer and Branch tokens. Without it, closure is disabled even on loopback. Viewer authorization and Branch ingest authorization remain separate.

The browser obtains the token through a password field, clears it before sending, and uses only the closure request Authorization header. URLs, browser storage, DOM text, and logs never contain it. Replay and demo cannot close live records. [Installation](../install.md#68-close-a-branch-or-project) defines operation and rotation.

Actual reopening increments a persistent counter, supporting notification deduplication when several state changes share one live update. Browser and ntfy alerts retain opt-in, baseline, replay suppression, queue, and rate-limit behavior. A qualifying Collector reconnect snapshot can notify; HQ restart itself cannot.

## Consequences

Closed records remain visible and retain history. A Project can reopen from a report on any known Branch. Closure never pauses a Collector or changes an Employee's observed work. A newly accepted delayed report can reopen a record; repeated unchanged idle polls cannot. Administrators must protect a separate credential and use HTTPS or trusted loopback transport.

## Alternatives Considered

Collector-owned closure would be overwritten by snapshots and would couple record management to host control. Viewer or Branch tokens would grant closure authority to read-only users or reporting hosts. Requiring fresh event_at or sent_at would incorrectly reject delayed observations and depend on Branch clock agreement. Treating heartbeat as agent observation would reopen idle records without an agent report.

## Verification Or Enforcement

The real HQ ingest, closure, state, changes, work-log, WebSocket, and ntfy paths are exercised by tests/integration/test_lifecycle.py. Upgrade inputs come from the real published 0.3.0 writer, preserving original database and API identities. Chromium tests exercise shipped closure controls and browser notification behavior at 1440px and 720px, substituting only the outer Notification boundary and clock. CLI checks exercise private token validation before HQ startup.
