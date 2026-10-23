# Office Expansion for 0.4.0

Release line: 0.4.0
Milestone index: 0.4.0
Canonical path: `docs/milestone-0.4.0.md`
Canonical branch or ref: master
Git upstream: origin/master
Remote tracker: none

Next session entry point: M1 implementation, T1-T8 verification, and both independent rechecks are accepted. Prepare its commit and upstream landing under separate git authority; M1 remains In progress until landing evidence exists. M2-M4 have not started.

## Scope

This document tracks Branch and Project lifecycle, meeting rooms, the Town map, and seasonal presentation.

Out of scope: implementing 0.4.0 during the 0.3.0 work, and release publication.

## Milestone

### Work

| ID | Work unit | Type | Status | Ready | Deps | Done when / Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| M1 | Branch and Project lifecycle | Milestone | In progress | No | [0.3.0 M3](milestone-0.3.0.md#m3---remote-development-environments), D1, D2, D3, D4 | Closure and observed automatic reopening work at HQ; [detail](#m1---branch-and-project-lifecycle) |
| M2 | Meeting rooms | Milestone | Not started | No | M1, D1 | Concurrent colleagues of one Project share the intended presentation; [detail](#m2---meeting-rooms) |
| M3 | Town map | Milestone | Not started | No | M2, D1 | Multiple Branches are navigable on the map; [detail](#m3---town-map) |
| M4 | Seasons and weather | Milestone | Not started | No | M3, D1 | Visual settings affect presentation consistently; [detail](#m4---seasons-and-weather) |

### Decisions

| ID | Decision | Decision Date |
| --- | --- | --- |
| D1 | Execute 0.4.0 after 0.3.0, in order M1, M2, M3, then M4. | 2026-10-22 |
| D2 | Require a separate administrator token to close a Branch or Project at HQ. Viewer access alone does not authorize closure. | 2026-10-22 |
| D3 | Reopen a closed Branch or Project when an on-duty agent is observed again, including an idle agent. A new shift or new work is not required. | 2026-10-22 |
| D4 | Use HQ receipt of a newly accepted qualifying agent/activity report or snapshot as the reopening observation. Unchanged idle polls that emit only heartbeat do not reopen records. Include the real 0.3.0 database-upgrade check and browser Notification check in the plan. | 2026-10-22 |

### Milestone Details

#### M1 - Branch and Project Lifecycle

Origin: 0.4.0 / M1
Identity History: none
GitHub Issue: none
Status: In progress

##### Summary

Let an owner close a Branch or Project at HQ and reopen it when an agent is observed there.

##### Scope

HQ persistence, owner actions, visible closed state, automatic reopening, and reopening notifications.

Out of scope: sending commands to Branches or terminating agents.

##### Completion Criteria

- Closed records remain persisted without affecting Branch processes.
- New agent observation reopens the record and produces the specified notification.
- State, history, authorization, and UI agree about lifecycle behavior.
- Closure requires the separate administrator token; viewer access alone cannot close records.
- An idle on-duty observation qualifies for reopening under D3; heartbeat alone and duplicate messages do not.

##### Dependencies And Decisions

- D1 sets work ordering after `docs/milestone-0.3.0.md` M3 completes.
- D2 separates administrator authorization for closure from viewer access. The accepted plan defines token configuration and UI handling.
- D3 includes idle on-duty observations in automatic reopening. Closing a record does not stop the agent; its next qualifying observation may reopen the record.
- D4 selects the HQ report boundary and accepts both initial verification-plan corrections. Lifecycle ordering uses HQ acceptance and receipt, independently of the Branch's fact or send clock; fact timestamps continue to serve observed activity history.

##### Plan Review

Observed At: 2026-10-23 01:28 UTC
Baseline: `47bc5b29154348aa869ec6b5cb8cab1ab7081015`
Frozen input SHA-256: `f0494ae2288a362c70371f085ab6948fdf3ccc31f9aaa75bcf1ff9f4aaab95f5`
Local review session: `work/review_sessions/20261023_004636_lifecycle/`
Workflow: L-size, Mode B, two independent reviewers; per-milestone commit preparation. The user confirmed the root agent as Facilitator.

| Pass | Person | Artifact ID | Must-Fix | Minor | Info | Hygiene | Other |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Third-person, delegated | rev20261023_005813 | 0 | 1 | 0 | 0 | 0 |
| 2 | Second-person, delegated | rev20261023_005339 | 0 | 1 | 0 | 0 | 0 |
| 3 | Third-person recheck, delegated | fup20261023_012120 | 0 | 0 | 0 | 0 | 0 |
| 4 | Second-person recheck, delegated | fup20261023_012553 | 0 | 0 | 0 | 0 | 0 |

| Item | Verified Plan Gap Or Question | Disposition |
| --- | --- | --- |
| F-codex_gpt6_state-001 | The plan promises preservation of existing SQLite data, but T2/T4/T5 did not name a database produced by the real 0.3.0 writer as an upgrade input. | Accepted under D4; T2 corrected and accepted in fup20261023_012120. Runtime upgrade verification passed in the Verification Results below. |
| F-codex_gpt6_auth-001 | Step 5 includes browser reopening notifications, but T6/T7 did not require observing the browser Notification path. | Accepted under D4; T7 corrected and accepted in fup20261023_012553. Runtime browser verification passed in the Verification Results below. |
| Q-state-001 | Real Collector diagnostics show that unchanged idle polls emit only heartbeats, and a newly discovered idle agent can report an older event_at with a new sent_at. Define the HQ observation boundary and freshness/ordering rule. | D4 selects a newly accepted HQ report. Qualification uses HQ acceptance/receipt order, not the age of event_at or sent_at; both rechecks accepted the clarification. |

Review state: both initial minor findings are resolved in the written plan, and the final third-person and second-person rechecks report zero remaining findings. The loop ended after cumulative review 4 with no finding above the floor; direct passes 0, delegated passes 4. D4 changed the observation contract after pass 2; the corrected plan remained unchanged between passes 3 and 4. Convergence is recorded in `convergence/conv20261023_012854_codex_gpt6_root_supersedes_conv20261023_012810.md` under the local session. Owner acceptance and execution authorization were subsequently granted on 2026-10-22 by reply "1"; root may combine Facilitator and Implementer. Real Collector diagnostics used the unchanged shipped Claude S01 session fixture and outer filesystem/clock controls; four existing history tests passed. These checks establish baseline premises only. At the plan-review boundary, M1 T1 through T8 were unexecuted and product code was unchanged. Subsequent authorized implementation and observed verification are recorded below; running user services remain unchanged.

##### Implementation Plan

Plan Status: accepted
Plan Acceptance: 2026-10-22; owner reply "1" accepting the reviewed canonical M1 plan.
Implementation Authorization: 2026-10-22; owner reply "1" authorizes M1 and root Facilitator/Implementer combination.
Superseded Plan Artifacts: none

1. Apply D3 and D4 to newly accepted agent messages identifying an on-duty agent, activity messages associated with that agent's current instance, and accepted snapshots containing on-duty agents, including idle agents. A qualifying observation reopens its Branch and Project if closed. Heartbeat, Branch metadata, off-duty observations, duplicates, and stale or rejected messages do not qualify. Qualify in HQ transaction/receipt order after closure, not by comparing old event_at or Branch sent_at with HQ closure time. Thus a newly accepted delayed report may reopen a record, while a replayed duplicate or stale report cannot. Record lifecycle transitions at HQ time in transaction order; do not alter the fact timestamps used for activity history. An unchanged idle poll that emits only heartbeat leaves closure intact. No Collector polling or delivery mechanism changes are planned.
2. In `hq/main.py` and `hq/app.py`, add a private administrator-token file and a separate authorization dependency for closure endpoints. Without an administrator token, closure is disabled even on loopback. Viewer and Branch credentials alone must not authorize closure. Keep existing read and ingest authorization intact, and validate the administrator token configuration before starting HQ.
3. In `hq/store.py`, persist HQ-owned Branch and Project lifecycle independently of Collector payloads, with transactional closure and reopening. A Project is global across Branches by architecture Section 1.3; snapshots cannot erase its closure record. Preserve existing SQLite data and initialize existing records as open. Repeated closure must not create additional transitions; reject unknown targets. Closing a Branch must not implicitly close its Projects or change their agents' observed presence and activity.
4. Extend `hq/store.py` and `hq/history.py` so live state, state-at-time, changes, checkpoints, and retention preserve lifecycle transitions. Record owner actions at HQ time and prevent delayed Collector timestamps from placing a reopening before its closure. Preserve agent work-log measurements and historical access to closed records.
5. In `hq/app.py`, `hq/notify.py`, and `hq/web/notify.js`, publish lifecycle changes to live viewers and notify on an actual reopening, including one caused by an accepted reconnect snapshot. Duplicate, stale, or rejected messages must not reopen records or create duplicate notifications. Keep existing notification opt-in, rate limits, and non-blocking delivery; external notifications use the configured ntfy transport.
6. In `hq/web/app.js` and the existing UI assets, show closed Branches and Projects distinctly, retain access to their history, and provide administrator-authorized closure controls. Take the administrator token through a password input, keep it only in page memory, and send it only as an authorization header on closure requests. Do not place it in URLs, browser storage, DOM text, or logs. Disable closure during replay and in the demo; preserve narrow-screen and keyboard behavior. Update the existing English and Korean UI dictionaries using the repository's current format.
7. Update `docs/architecture.md` and `docs/protocol.md` for the HQ-owned lifecycle and unchanged Collector wire contract. Document administrator-token startup and UI operation in `docs/install.md`, which owns HQ CLI/token instructions; keep `docs/configuration.md` focused on Collector configuration. Promote the lifecycle, ordering, schema, and access decisions to `docs/decisions/ADR-20261022-hq-lifecycle.md` and its `README.md` index. Implement the focused real-path checks in `tests/integration/test_lifecycle.py` and `tests/browser/test_lifecycle.py`, using the existing unit tests where appropriate. Run T1 through T8 against the real HQ, storage, transport, and browser paths, then record observed results here. Review this durable state and schema change before implementation and recheck the finished change against the accepted plan.

Verification commands from the repository root; observed results follow:

```bash
.venv/bin/python -m pytest -q tests/integration/test_lifecycle.py
.venv/bin/python -m pytest -q tests/browser/test_lifecycle.py
.venv/bin/python -m pytest -q --junitxml=work/pytest-040-m1.xml
mdbook build
```

Plan-time premises: `hq/main.py` loaded private viewer and Branch token files; `hq/app.py` authorized only reads and ingest. `hq/store.py` replaced Collector-owned Branch payloads on snapshots and records changes through checkpoints and retention. `collector/main.py` sends heartbeat intervals without agent content. `hq/web/app.js` derived Projects from agents, while `hq/notify.py` and `hq/web/notify.js` had no lifecycle subject. These are implementation premises, not verification results for this milestone.

##### Test Plan

| Label | Layer | Method | Environment | Expected Result |
| --- | --- | --- | --- | --- |
| T1 | Integration | Start the real HQ with separate administrator, viewer, and Branch credentials; call closure endpoints with each credential and without one | Isolated HQ process and SQLite database | Only the administrator credential closes a known target; missing administrator configuration disables closure; read and ingest authorization remain unchanged |
| T2 | Integration | Generate a preserved database with the real published 0.3.0 writer at 2f9fb6b73224bd1f8612b5be74bce5c87b8f7dcf, then open a copy with M1; compare pre-upgrade API-visible state, state-at-time, changes, history range, and work log; close Branches and the shared Project, repeat closure, cross retention, and restart | Isolated old-writer and M1 HQ environments; two Branches sharing one Project; on-duty and off-duty agents, activities, existing changes, checkpoints, and a retained baseline; old source, DB, and expected-response identities retained | Existing observation fields, identities, history, and work-log measurements survive unchanged; new lifecycle metadata starts open; closure persists independently of snapshots and reachability; repeated closure adds no transition; unknown targets are rejected; no hand-built old schema substitutes for the old writer |
| T3 | Integration | Send qualifying observations and heartbeat, duplicate, stale, off-duty, delayed-fact, and clock-skewed envelopes through the real ingest endpoint; cover newly discovered idle agents, unchanged idle polls, and reconnect snapshots | Real Collector, shipped provider fixture, Envelope, HttpSender, and isolated HQ; only filesystem/process inputs and clocks controlled at their outer boundaries | New accepted on-duty reports and snapshots qualify in HQ receipt order even with older event_at or skewed sent_at; heartbeat-only repeated idle polls retain closure; duplicates, stale, and rejected messages retain closure; lifecycle history never moves before its preceding closure |
| T4 | Integration | Query state-at-time and changes before closure, after closure, and after reopening; cross checkpoint and retention boundaries, then restart | Real HQ history endpoints and SQLite | Lifecycle states and transition order agree with live state and remain reconstructible within retention |
| T5 | Integration | Read the real work-log endpoint over a period containing closure and reopening | Real HQ ingest and history with deterministic outer clock | Closure leaves observed employee presence, activity, identities, and accumulated work-log measurements intact |
| T6 | Integration | Trigger reopening through ingest and a reconnect snapshot; receive WebSocket updates and ntfy HTTP requests at a local test server | Real HQ notification loop, Notifier, Outbox, and HTTP transport | The reopening is visible and notified without duplicate messages; existing delivery limits and opt-in behavior are preserved |
| T7 | UI | Use real closure controls with and without administrator credentials; enable notifications in the shipped settings; trigger Branch and Project reopening through real ingest including a reconnect snapshot; observe Notification count/content, duplicates, opt-in off, replay/demo suppression, and delivery limits; inspect closed history, keyboard access, and narrow layout | Chromium with real HQ at 1440px and 720px; actual WebSocket, app.js, and notify.js; observe or substitute only the outer browser Notification boundary and outer clock | Authorized closure and reopening appear correctly; browser alerts identify the expected subject without duplicates and respect opt-in, replay/demo, and delivery limits; closed history remains accessible; replay and demo cannot mutate live records; token stays out of URLs and browser storage |
| T8 | Regression | Run the shipped test suite and documentation build after the focused lifecycle checks | Repository test environment and mdBook | Existing observation, history, notification, browser, and installation behavior continues to pass; documentation builds |

##### Verification Results

| Label | Observed At | Environment | Result | Evidence |
| --- | --- | --- | --- | --- |
| T1 | 2026-10-23 02:44-02:45 UTC | HQ CLI process and HTTP | Passed | Separate administrator/viewer/Branch authorization, missing configuration, seven unsafe-token startup cases, and malformed Origin 403/no mutation/continued serving; `work/pytest-040-m1-corrected.xml`; real fixtures and databases retained under `/tmp/pytest-of-jeonglee/pytest-32/` |
| T2 | 2026-10-23 02:07-02:10 UTC | Published 0.3.0 writer and M1 HQ | Passed | Real source 2f9fb6b73224bd1f8612b5be74bce5c87b8f7dcf generated the upgrade DB; original source, database hashes, and API expectations retained; `work/pytest-040-m1-final.xml`; real fixtures and databases retained under `/tmp/pytest-of-jeonglee/pytest-29/` |
| T3 | 2026-10-23 02:07-02:10 UTC | Collector, shipped Claude S01, HTTP HQ | Passed | Unchanged idle heartbeat, newly discovered idle agent, duplicate/stale/off-duty/current-instance handling, delayed/skewed reports, and empty snapshot preservation; `work/pytest-040-m1-final.xml`; real fixtures and databases retained under `/tmp/pytest-of-jeonglee/pytest-29/` |
| T4 | 2026-10-23 02:07-02:10 UTC | SQLite, checkpoints, retention, HTTP history | Passed | Live and historical lifecycle, global Project membership filtering, retention, and restart; `work/pytest-040-m1-final.xml`; real fixtures and databases retained under `/tmp/pytest-of-jeonglee/pytest-29/` |
| T5 | 2026-10-23 02:07-02:10 UTC | Real HTTP work-log endpoint | Passed | Observation fields and work-log totals survive closure/reopening and old-database upgrade; `work/pytest-040-m1-final.xml`; real fixtures and databases retained under `/tmp/pytest-of-jeonglee/pytest-29/` |
| T6 | 2026-10-23 02:07-02:10 UTC | Real WebSocket, Notifier, Outbox, ntfy HTTP | Passed | Reopening and reconnect snapshot, duplicate suppression, 30-second delivery limit, and cancellation after reclosure; `work/pytest-040-m1-final.xml`; real fixtures and databases retained under `/tmp/pytest-of-jeonglee/pytest-29/` |
| T7 | 2026-10-23 06:47:06 UTC | Chromium 1440px/720px; actual HQ and outer HTTP delivery timing | Passed; independently accepted | All 12 browser cases passed; eight added cases cover Branch/Project reopening or actual disconnect with delayed real HTTP bytes, one notification and immediate reclosure. Four reopen cases failed before correction. work/pytest-040-m1-refresh-after.xml and refresh-before-valid.xml (prefix pytest-040-m1-). Prior independent failure is retained below. |
| T8 | 2026-10-23 06:47:06 UTC | Repository, mdBook, isolated installed prefix | Passed; independently accepted | Whole suite 317 passed, zero skipped/failures/errors, 58.15 s; work/pytest-040-m1-refresh-full.xml. mdbook build and git diff --check passed. Corrected installed prefix console/API/Origin/static serving passed; full app.js body equals source. work/m1-install-f_ojpnra/receipt.json; runtime dependencies supplied by existing .venv. |

##### Implementation Review

Observed At: 2026-10-23 02:30:55 UTC
Target: frozen 22-file M1 implementation at baseline 47bc5b29154348aa869ec6b5cb8cab1ab7081015.
Author retrospective: hand20261023_021217, cumulative implementation review 1; no further code changes.
Independent report: rev20261023_022805, cumulative implementation review 2, third-person delegated.

| Finding | Classification | Observable Result | State |
| --- | --- | --- | --- |
| F-codex_gpt6_state-002 | minor | Authenticated malformed Origin http://[ returns 500 at the new closure endpoint instead of documented 403; parser ValueError; no unauthorized mutation or data loss observed | implemented and independently verified in fup20261023_025553; no remaining finding in Lane A |
| F-codex_gpt6_auth-002 | minor | A delayed real closure HTTP refresh restores Closed and disables its control after WebSocket has already reported reopening; backend remains open; measured periodic recovery 10.391 s | implemented and independently verified in fup20261023_065521 and fup20261023_065936; no remaining finding |

The independent reviewer read all 22 frozen files, verified their hashes, and ran all 308 tests successfully in 43.30 seconds. Additional actual HTTP checks passed for same-instant global Project transitions through both Branch filters, empty snapshots, work-log preservation, retention/checkpoints, and restart. mdBook and a fresh isolated installed prefix passed. The malformed-Origin defect came from an additional real uvicorn request outside the original test cases. Local report: work/review_sessions/20261023_004636_lifecycle/reviews/rev20261023_022805_codex_gpt6_state_implementation.md; actual HTTP evidence: /tmp/agentville-m1-review-native.XKc6ia/boundary-receipt.json and boundary-source.log.

Second-person operator review subsequently completed as recorded below. The owner accepted the Origin correction/recheck by reply 1. The real endpoint regression reproduced HTTP 500 before correction and passed with HTTP 403, unchanged lifecycle, and subsequent normal closure after correction. The whole corrected suite passed 309 tests in 40.22 seconds (work/pytest-040-m1-corrected.xml). Only hq/app.py and tests/integration/test_lifecycle.py changed; the new frozen handoff hand20261023_024630 records this accepted correction. Independent recheck fup20261023_025553 passed with no findings. It reran all 309 tests in 44.68 seconds and independently verified six malformed/foreign Origin values through real HTTP and WebSocket, credential separation, configured server names, no mutation, and subsequent normal closure/reopening. Evidence: /tmp/agentville-m1-origin-review.7sdfuK/origin-matrix.json and results.xml. The separate four-pass plan review remains converged.

```text
--   ------   --------   -----   ----   -------   -----   ------------------------------------
No   Person   Must-Fix   Minor   Info   Hygiene   Other   Description
--   ------   --------   -----   ----   -------   -----   ------------------------------------
 1   3rd             0       1      0         0       0   Whole artifact, Lane A delegated
 2   3rd[c]          0       0      0         0       0   Protected HQ boundary, delegated
 3   2nd             0       1      0         0       0   Operator UI path, delegated
 4   3rd[c]          0       0      0         0       0   Partial HTTP body, delegated
 5   2nd[c]          0       0      0         0       0   Slow/interrupted operator, delegated
--   ------   --------   -----   ----   -------   -----   ------------------------------------
     Total           0       2      0         0       0   all 5 passes
```

Open 0   Artifact Unchanged yes

Cumulative 6th review of the implementation target   Direct 1   Delegated 5
Termination: no finding above the floor in either assigned recheck. Both historical minor findings are corrected and independently verified; no new decision changed the target.

The preceding correction/recheck cycle stopped with the UI finding returned to the owner. Owner reply 1 explicitly authorized its correction and the next bounded cycle. Reviews 5 and 6 now both pass; the completed four-pass plan review is a separate target.

Second-person review rev20261023_030835 completed with must-fix 0, minor 1, and other counts 0; verdict changes requested. Its unmodified browser run returned 3 passed and 1 failed in 15.58 seconds, at the 720px Branch reopening display. A separate actual response-order reproduction held the unchanged bytes of a real closed-state HTTP response at the outer transport boundary, allowed actual ingest and WebSocket to reopen at revision 2, then released revision-1 HTTP bytes. The screen returned to Closed with a disabled control while the backend remained open, recovering after 10.391 seconds on a periodic update. No internal production function or hand-built state response replaced the path. Evidence: /tmp/agentville-operator-auth.mgmqXK/browser.xml and browser.stdout; /tmp/agentville-response-order._ptaj0ud/response-order.json, verify.stdout, and stale-closed-after-reopening-720.png. Official report: work/review_sessions/20261023_004636_lifecycle/reviews/rev20261023_030835_codex_gpt6_auth_implementation.md.

The independent operator CLI setup, credential rotation, private-file checks, history and token-exposure checks passed; those successes do not cancel the UI defect. The earlier 309-pass whole-suite results remain historical observations of their actual runs. That pass failed T7 and UI regression acceptance on its reviewed target; the owner-approved correction and fresh author verification are recorded below, without claiming independent acceptance prematurely.

The first correction/recheck cycle stopped with Origin resolved and the new UI finding returned to the owner. The owner subsequently selected option 1, explicitly authorizing its correction and the next bounded recheck cycle. The UI now captures the live-state object before requesting an HTTP refresh and applies the response only while still connected with that same live object. New actual-HTTP/WS regressions failed on all four reopen cases before correction and passed after it. The original failed evidence remains preserved; no backend policy changed. Independent reviews 5 and 6 both passed on hand20261023_064431, as recorded below.

Current author verification after the accepted UI correction: 12 browser cases passed in 25.31 seconds; whole suite 317 passed in 58.15 seconds, no failures/errors/skips. Evidence: work/pytest-040-m1-refresh-before-valid.xml, refresh-after.xml, and refresh-full.xml (full prefixes pytest-040-m1-). Actual fixture outputs and screenshots: /tmp/pytest-of-jeonglee/pytest-36. New installed-prefix receipt work/m1-install-f_ojpnra/receipt.json confirms that HTTP app.js bytes equal the corrected source, normal HQ closure and static serving work, and prior Origin rejection remains intact. mdBook and diff checks passed after the correction. These are author verification results. Independent acceptance is recorded separately below.

Latest implementation acceptance observed at 2026-10-23 07:01:24 UTC. Third-person follow-up fup20261023_065521 reread the full frozen artifact/spec and independently passed all 317 tests in 54.29 seconds, four additional protected partial-body/HTTP-only cases, and mdBook. Second-person follow-up fup20261023_065936 passed all 12 browser cases in 25.93 seconds and two new protected operator paths: navigation/history with reopening and immediate reclosure, and actual disconnect with continued action blocking. Both verified the accepted UI correction and reported zero must-fix, minor, info, hygiene, or other findings. The second-person pass did not rerun the full suite, old-writer upgrade, or ntfy; those are independently rerun in the third-person suite.

Evidence: work/review_sessions/20261023_004636_lifecycle/reviews/fup20261023_065521_codex_gpt6_state_on_hand20261023_064431.md and fup20261023_065936_codex_gpt6_auth_on_hand20261023_064431.md; /tmp/agentville-m1-refresh-review.LqE40B/results.xml and body-matrix.json; /tmp/agentville-auth-recheck6.paeF13/receipt.json. Final source hash check matched all 22 frozen files. Facilitator acceptance: cmt20261023_070124; no additional review pass is claimed.

##### Closure Evidence

- Completed response-order regression inputs, raw HTTP bodies, screenshots, databases, and before/after/full XML are copied and SHA-256-checked outside pytest automatic cleanup at work/evidence/m1-refresh-20261023_065026/receipt.json. The actual pre-correction app.js from an earlier installed-source copy matches the preceding frozen manifest and is retained there. Five ended socket paths are recorded as metadata only; no endpoint recreation or replay is claimed.

- Corrected package installation verified at 2026-10-23 02:58:34 UTC in an isolated prefix; actual launcher, malformed-Origin rejection, unchanged state, normal closure, and static asset receipt: work/m1-install-wxv6ec08/receipt.json. Runtime prerequisites came from the existing .venv; no production installation or OS dependency bootstrap is claimed.
- Implementation verification and independent implementation acceptance passed; git commit and upstream landing remain pending. No commit, push, production installation, or user-service change was performed.
- Failed test attempts are retained. The sandbox run reported 296 passed and 12 Unix-socket permission failures; the unrestricted rerun passed all 308. The reclosure regression exposed extra ntfy/browser alerts before correction (`work/pytest-040-m1-reclose-before.xml`); the final real-path suite passed.
- M1 remains In progress until the required commit and upstream landing evidence exist. Review acceptance does not close the session or authorize M2.

#### M2 - Meeting Rooms

Origin: 0.4.0 / M2
Identity History: none
GitHub Issue: none
Status: Not started

##### Summary

Show colleagues working concurrently on the same Project in a meeting-room presentation.

##### Scope

Define participation, layout, capacity, and transitions, including any required artwork. Expand the office to support approximately 20 working colleagues and add one meeting room. Assign arriving colleagues to available desks without overlap; use available Fika seating instead of leaving colleagues standing. Verify character direction against each seat and sofa orientation.

Out of scope: recording a collaboration relationship merely because characters share a room.

##### Completion Criteria

- Participation follows the accepted same-Project concurrency rule.
- Entry and exit preserve selection, identity, accessibility, and reduced-motion behavior.
- Approximately 20 colleagues can work at distinct desks, including simultaneous arrivals, without overlap while suitable desks remain available.
- Fika colleagues use available seats and face the direction appropriate to each seat; standing is reserved for exhausted seating capacity.
- The office contains one meeting room with explicit seating capacity and entry and exit behavior.

##### Dependencies And Decisions

- M1 precedes M2 by D1; this is work ordering.
- Proposed for owner acceptance with this plan. Each proposal is accepted or rejected separately by owner reply and recorded in the Decisions table as D5, D6, D7. Every step names the proposals and steps it needs; a rejected proposal blocks those steps and every later step that depends on them.
  - P1 (annex). The existing `office.png` stays unchanged as the main office. The annex is one new generated image, `office-annex.png`, with two project studios (back-left studio A, back-right studio B, 6 desks each) and one meeting room, so the office has 20 desks: main-office studios 4 and 2, Common Office 2, annex studios 6 and 6. Same canvas (1536 x 1024) and furniture scale as the main office, so character, foot-box, and sprite sizes stay as they are.
    - What changes on the page: the annex is drawn below the main office in the office card whenever one of its rooms has occupants or a meeting is in progress; one page shows four Project rooms (main-office studios first, then annex studios, in the existing Project order) instead of two, and room navigation pages by four; a colleague moving between the main office and the annex is placed directly, without walking between the images; cats stay in the main office. The annex has its own scene: its own walk graph, footprints, furniture-front layers, depth order, window light (same light periods as the main office), and painting frames (paintings do not repeat within one scene).
    - Artwork source. The owner generates the image with the same OpenAI image generation used for the 0.1.0 artwork, following `docs/design/office-annex-artwork.prompt.txt`. No artwork is drawn by an agent or in code; overlays already drawn in code (decor, mugs, books, hard hat) stay overlays.
    - Image acceptance. The owner checks the "Required" list of the prompt file before handing the image over (by eye, and the scale item by measuring two desks in pixels); the implementer re-checks the measurable items (counts, chair directions, scale, clearances, corridor) in step 3. A miss of a required item means a new generation by the owner. Counts may differ within the tolerances listed there; the seat table and the tests follow the accepted image and the difference is recorded in the Verification Results. When three generations miss a required item, the owner rules on relaxing it.
    - Hand-over and landing. The owner commits and pushes the raw generator output as `packages/agentville/hq/web/office-annex.png` on branch `claude/modest-albattani-dn2ho3`. No code reads that file before step 4, so the page is unaffected by its arrival. A regenerated image replaces the file at the same path with a new commit and push. In step 3 the implementer converts it in place to the stored format of `docs/design/artwork.md` (palette-quantized PNG with alpha, losslessly optimized). M2 lands on master like earlier work, by merge; the raw image stays in the repository history (a few MB), which is accepted.
  - P2 (meeting participation). Presentation only, computed in the page from observed state; nothing is recorded, sent, or stored, and sharing the room implies no collaboration relationship.
    - Evaluated per Branch: each Branch has at most one meeting, computed on every state update for every Branch the page receives.
    - Eligible colleagues of a Branch: on duty, belonging to that Branch's office (local colleagues and remote colleagues of its Projects; a remote colleague can therefore be eligible on its home Branch and on the remote one), of a Project with a project room (not the Common Office, whose colleagues work outside any repository), not in a closed Project or Branch (M1). Eligibility does not depend on the displayed page or on "+N" collapsing.
    - Drawing: the displayed Branch's meeting is drawn in the annex meeting room on every page of that Branch, whatever page shows its Project's room. Members are drawn only at the table: never in their own room and never counted in its "+N".
    - Clock: the page's own wall-clock observation of each colleague's activity state, kept per colleague from the first live state the page receives after load or reconnect; it is not reset by a Branch or page change. `state_since` is not used, because the Collector restarts it on every tool start. After a load or reconnect no colleague qualifies until observed for the full entry time.
    - Entry: a Project meets when at least two eligible colleagues have been observed in `working` (or `thinking`) continuously for 60 s. Exit: a member leaves when observed in any other state for 30 s, or at once for `waiting`, `error`, `limited`, off duty, or loss of eligibility; it then goes where the existing rules place it (desk, Fika, infirmary, or not shown). The meeting ends when fewer than two members remain.
    - No preemption: a meeting in progress is not replaced by another Project. When none is in progress, the qualifying Project with the most qualifying colleagues starts, ties broken by the earliest time it qualified, then by Project id. Capacity C is the number of meeting chairs in the accepted image (target 6). Members are ordered by the start of their current continuous qualification, then by agent id, which does not depend on the displayed page; the first C are members, the others stay where the existing rules place them; a member leaving frees its chair for the next qualifying colleague of the same Project in that order. Chairs are taken in chair-index order.
    - A member that held a desk when it joined keeps that desk reserved (shown empty) until it leaves the meeting; a member that held none, or whose room's desk assignments started over after a Branch or page change, is assigned no desk while it meets and takes the lowest free desk of its room when it returns. Members stay members of their Project room for the room filter, the room-tab counts, search, and keyboard focus; the meeting room has no tab. At the table members are seated, keep their activity label and tool name, and show non-verbal bubbles as in the Lounge; there is no keyboard at the table, so no typing gesture.
    - Replay, demo, reduced motion, hidden views: no meeting is formed during replay (the replayed state is sampled once per minute); the default demo data (`/?demo=1`) shows one fixed meeting, listed in `demo.js` as data rather than formed by the timing rules, because demo mode receives a single state; with reduced motion members are placed directly; hidden views pause walking only.
  - P3 (seats). Every seat (desk chair, meeting chair, Fika seat, bed) is one entry of a seat table holding: id (room and index, e.g. `studio0.2`), scene (`main` or `annex`), position, depth, facing, approach waypoint, and for desks the workstation points (keyboard, mouse) and screen glass. What changes on the page: nothing in the main office; the annex seats use the same table. Facing values are those the sprites support: `front` (seated front frame), `back` (seated rear frame), their mirrors `front-right` and `back-left`, and `lying` for the bed. Arrival, overflow, and standing behaviour stays as architecture Section 6.2 states it: arrivals take the lowest free suitable seat of their room in seat-number order; a seat holds one colleague; desk rooms show further occupants as "+N"; Fika and the infirmary use standing spots only when all their seats are taken.

##### Implementation Plan

Plan Status: draft
Plan Acceptance: none
Implementation Authorization: none
Superseded Plan Artifacts: 4a9ca06 (single enlarged office image), b1b8132, f6ad683, 3d53496, 0428baf (annex plan before reviews 3-10)

1. Seat table in the main office (needs P3). The main office looks exactly as before; `front-right` becomes available for the annex. Move `ROOM_LAYOUT` seats, `WORKSTATIONS`, `SCREENS`, approach waypoints, depths, and facings into one seat table in a new `hq/web/seats.js`; make `app.js`, `sprites.js`, `furniture.js`, `lounge.js`, and `app.css` read only from it, including the mirrored arm, keyboard, book, and outline placement for `front-right` and `back-left`. Write T1 under `tests/browser` and record its baseline from the code before this step. Done when T1 passes.
2. Meeting membership (needs P2). Implement P2 as a pure function in `hq/web/meeting.js` over (state of all Branches, per-colleague observation times, the previous meeting of each Branch, now, mode, closed records, capacity) returning each Branch's meeting. Write the T2a test with it under `tests/browser`. Done when T2a passes.
3. Artwork intake (needs P1, P3, step 1, and the owner's raw image). Check the measurable "Required" items; a miss returns the image to the owner for a new generation and the step waits. Scale an accepted image of another 3:2 size to 1536 x 1024 and convert it in place to the stored format; record provenance in `docs/design/artwork.md`; measure on the annex: the floor outline, furniture footprints, furniture-front layers and depths, waypoints and links, every seat entry of P3 (including workstation points and screen glass), standing spots, "+N" anchors, painting frames, and window glass. Add the route clearance test under `tests/browser` for both scenes: every graph link and straight step sweeps the foot box without touching a footprint, and every seat step touches only its own seat's chair, sofa, or bed and, at a desk, the desk the chair belongs to (architecture Section 6.2). Done when the Required items are confirmed, the stored image is converted and its provenance recorded, every list above has annex values, the measured counts are recorded in the Intake row of Verification Results, and the route clearance test passes.
4. The annex in the office card (needs steps 1 and 3). A second scene element with its own character layer and stacking context below the main office; four Project rooms per page; direct placement between the scenes; window light and paintings in the annex. Write T3 and T7 under `tests/browser`. Done when T3 and T7 pass.
5. Meeting room (needs steps 2 and 4). Draw the displayed Branch's meeting, route members to the meeting chairs and back, keep their desks reserved, draw bubbles. Add the fixed meeting of `/?demo=1` and the demo variants `/?demo=seats` (every desk, Fika seat, and bed of both scenes occupied, no meeting) and `/?demo=meeting` (a meeting filling every meeting chair), with the demo check in `app.js` accepting them. Write T2b, T4, and T5 under `tests/browser`. Done when T2b, T4, and T5 pass.
6. CI and documentation (the CI job needs nothing; the documentation covers the steps carried out). Add a CI job that installs `.[hq,test,browser]` and the Playwright Chromium (`playwright install --with-deps chromium`) and runs `tests/browser`, where every Chromium-run test of M2 lives, with `AGENTVILLE_REQUIRE_BROWSER=1`; replace the `pytest.importorskip` of the browser tests so that under that variable a missing Playwright fails instead of skipping. Update architecture Sections 2.4, 6.2, 6.3, 6.5 (no meetings in replay), and 9.1, using.md (the annex, meeting room, capacities; the word "floor" keeps its page sense), the manual screenshots, and the 0.4.0 CHANGELOG entry. Done when T6 passes in CI.

##### Test Plan

| Label | Layer | Method | Environment | Expected Result |
| --- | --- | --- | --- | --- |
| T1 | UI | Before and after step 1, open `/?demo=1` with reduced motion at 1440 px and 720 px and record each drawn colleague's room and seat index, facing, frame, mirror, and bounding box; compare | Chromium through pytest | Identical records; no console errors |
| T2a | Unit | Import `meeting.js` in Chromium and feed observed-state sequences: entry at 60 s, exit at 30 s and immediate exits, no preemption, tie rules, capacity C with members ordered by the start of their continuous qualification then agent id and chairs taken in chair-index order, Common Office and closed Project exclusion, colleagues collapsed into "+N", reload and reconnect (clock restart), Branch and page change (no clock reset), replay | Chromium through pytest | Membership follows P2 in every case |
| T2b | UI | Drive the T2a sequences through real HQ ingest and WebSocket on the rendered office; change the room page and apply a Project-room filter and search while a meeting is in progress; open `/?demo=1` | Chromium; real HQ; both scenes | Drawn members match T2a, allowing for live updates every 10 s; the meeting stays drawn on every page; at the table members show their activity label, tool name, and bubbles and no typing gesture; members stay selectable, focusable, counted in their Project room, and undimmed under their room's filter; the default demo shows its fixed meeting; HQ state and history are unchanged by meetings |
| T3 | UI | Ingest 18 on-duty colleagues over four Projects (4, 2, 6, 6, or the measured studio sizes) plus 2 in the Common Office, 20 in all, in one batch and in several batches; then departures and new arrivals; then one more colleague in a full room | Chromium; real HQ; both scenes | Distinct desks without overlap; freed desks reused; "+N" only in a room whose desks are all taken |
| T4 | UI | Move colleagues into Fika, the infirmary, and the meeting room through real activity updates, including more than the capacity of each; repeat with reduced motion | Chromium; real HQ | Seats are used before standing spots; capacities hold; desks stay reserved during meetings; with reduced motion every move places the colleague directly |
| T5 | UI and owner | Open `/?demo=seats` (desks, Fika seats, beds) and `/?demo=meeting` (meeting chairs); capture one screenshot per room with seat ids; the owner confirms each figure faces its chair, sofa, bed, or table | Chromium; owner review | Owner confirmation recorded per seat; this is the direction check, independent of the seat table |
| T7 | UI | With live data: no annex occupant and no meeting, then one annex occupant; the four light periods by Branch time; the annex paintings | Chromium; real HQ | The annex is hidden when empty and shown otherwise; annex window light follows the light period like the main office; no painting repeats within the annex |
| T6 | Regression | Route clearance test on both scenes; whole test suite including `tests/browser` in the CI browser job; mdBook | Repository and CI | No route crosses a footprint; existing behaviour passes; browser tests run, not skipped |

##### Verification Results

| Label | Observed At | Environment | Result | Evidence |
| --- | --- | --- | --- | --- |
| Intake | Not run | Owner image | Pending | measured studio A, studio B, and meeting-chair counts; generation attempts |
| T1 | Not run | Browser | Pending | none |
| T2a | Not run | Browser | Pending | none |
| T2b | Not run | Browser | Pending | none |
| T3 | Not run | Browser | Pending | none |
| T4 | Not run | Browser | Pending | none |
| T5 | Not run | Browser and owner | Pending | none |
| T6 | Not run | Repository and CI | Pending | none |
| T7 | Not run | Browser | Pending | none |

##### Closure Evidence

- none

#### M3 - Town Map

Origin: 0.4.0 / M3
Identity History: none
GitHub Issue: none
Status: Not started

##### Summary

Provide a map for navigating multiple Branches and opening their offices.

##### Scope

Branch representation, reachability, selection, navigation, and equal-alias disambiguation.

Out of scope: inferring geographic coordinates from fictional location labels.

##### Completion Criteria

- Every displayed Branch can be selected and opened in its office view.
- Equal aliases and unreachable or closed Branches remain distinguishable.
- Navigation works on narrow screens and with keyboard input.

##### Dependencies And Decisions

- M2 precedes M3 by D1; this is work ordering.

##### Implementation Plan

Plan Status: draft
Plan Acceptance: none
Implementation Authorization: none
Superseded Plan Artifacts: none

1. Define map positioning and navigation rules.
2. Implement the accepted Branch map.
3. Verify navigation, status changes, and accessibility.

##### Test Plan

| Label | Layer | Method | Environment | Expected Result |
| --- | --- | --- | --- | --- |
| T1 | UI | Render several Branches and navigate by pointer and keyboard | Browser | Correct office opens; status and identity remain clear |

##### Verification Results

| Label | Observed At | Environment | Result | Evidence |
| --- | --- | --- | --- | --- |
| T1 | Not run | Browser | Pending | none |

##### Closure Evidence

- none

#### M4 - Seasons and Weather

Origin: 0.4.0 / M4
Identity History: none
GitHub Issue: none
Status: Not started

##### Summary

Extend the office's visual presentation with seasons and weather.

##### Scope

Define visual settings, time-zone behavior, and reduced-motion presentation.

Out of scope: changing Collector observations, colleague activity, or provider state.

##### Completion Criteria

- Seasons and weather follow the accepted display rules.
- Replay, Branch time, reduced motion, and narrow layouts remain consistent.

##### Dependencies And Decisions

- M3 precedes M4 by D1; this is work ordering.

##### Implementation Plan

Plan Status: draft
Plan Acceptance: none
Implementation Authorization: none
Superseded Plan Artifacts: none

1. Define settings and deterministic display rules.
2. Implement the accepted visuals.
3. Verify live, replay, and reduced-motion presentation.

##### Test Plan

| Label | Layer | Method | Environment | Expected Result |
| --- | --- | --- | --- | --- |
| T1 | UI | Render settings across Branch time zones, replay, and reduced motion | Browser | Visuals follow settings without changing observations |

##### Verification Results

| Label | Observed At | Environment | Result | Evidence |
| --- | --- | --- | --- | --- |
| T1 | Not run | Browser | Pending | none |

##### Closure Evidence

- none

## Backlog

### Work

| ID | Work unit | Type | Status | Ready | Deps | Done when / Evidence |
| --- | --- | --- | --- | --- | --- | --- |

### Backlog Details

No unassigned work.
