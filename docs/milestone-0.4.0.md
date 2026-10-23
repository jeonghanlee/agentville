# Office Expansion for 0.4.0

Release line: 0.4.0
Milestone index: 0.4.0
Canonical path: `docs/milestone-0.4.0.md`
Canonical branch or ref: none
Git upstream: none
Remote tracker: none

Next session entry point: Plan M1 against docs/architecture.md Section 1.8 and the current HQ authorization, persistence, history, and notification code. AgentVille 0.3.0 is published and released-tag installation passed; M1 dependencies are complete. Resolve who may close records and which new observation reopens them before accepting the detailed implementation and real-path test plan. Office capacity, seating, Fika direction, and one meeting room remain in M2.

## Scope

This document tracks Branch and Project lifecycle, meeting rooms, the Town map, and seasonal presentation.

Out of scope: implementing 0.4.0 during the 0.3.0 work, and release publication.

## Milestone

### Work

| ID | Work unit | Type | Status | Ready | Deps | Done when / Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| M1 | Branch and Project lifecycle | Milestone | Not started | Yes | [0.3.0 M3](milestone-0.3.0.md#m3---remote-development-environments), D1 | Closure and observed automatic reopening work at HQ; [detail](#m1---branch-and-project-lifecycle) |
| M2 | Meeting rooms | Milestone | Not started | No | M1, D1 | Concurrent colleagues of one Project share the intended presentation; [detail](#m2---meeting-rooms) |
| M3 | Town map | Milestone | Not started | No | M2, D1 | Multiple Branches are navigable on the map; [detail](#m3---town-map) |
| M4 | Seasons and weather | Milestone | Not started | No | M3, D1 | Visual settings affect presentation consistently; [detail](#m4---seasons-and-weather) |

### Decisions

| ID | Decision | Decision Date |
| --- | --- | --- |
| D1 | Execute 0.4.0 after 0.3.0, in order M1, M2, M3, then M4. | 2026-10-22 |

### Milestone Details

#### M1 - Branch and Project Lifecycle

Origin: 0.4.0 / M1
Identity History: none
GitHub Issue: none
Status: Not started

##### Summary

Let an owner close a Branch or Project at HQ and reopen it when an agent is observed there.

##### Scope

HQ persistence, owner actions, visible closed state, automatic reopening, and reopening notifications.

Out of scope: sending commands to Branches or terminating agents.

##### Completion Criteria

- Closed records remain persisted without affecting Branch processes.
- New agent observation reopens the record and produces the specified notification.
- State, history, authorization, and UI agree about lifecycle behavior.

##### Dependencies And Decisions

- D1 sets work ordering after `docs/milestone-0.3.0.md` M3 completes. Detailed lifecycle and authorization decisions remain for planning.

##### Implementation Plan

Plan Status: draft
Plan Acceptance: none
Implementation Authorization: none
Superseded Plan Artifacts: none

1. Specify lifecycle transitions and owner authorization.
2. Define persistence, API, history, notification, and UI changes.
3. Implement and verify the accepted plan.

##### Test Plan

| Label | Layer | Method | Environment | Expected Result |
| --- | --- | --- | --- | --- |
| T1 | Integration | Close and reopen through real HQ endpoints and ingest | Isolated HQ database | Authorized closure persists; observation reopens and notifies |

##### Verification Results

| Label | Observed At | Environment | Result | Evidence |
| --- | --- | --- | --- | --- |
| T1 | Not run | HQ | Pending | none |

##### Closure Evidence

- none

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

##### Implementation Plan

Plan Status: draft
Plan Acceptance: none
Implementation Authorization: none
Superseded Plan Artifacts: none

1. Define participation, the 20-colleague office layout, one meeting room, seat orientation, and artwork requirements.
2. Implement the accepted layout, available-seat assignment, and transition behavior.
3. Verify 20 simultaneous arrivals, departure and seat reuse, Fika seating and direction, meeting-room capacity, and reduced motion.

##### Test Plan

| Label | Layer | Method | Environment | Expected Result |
| --- | --- | --- | --- | --- |
| T1 | UI | Render simultaneous same-Project colleagues and change their activity | Browser | Correct membership and transitions without changing observed data |
| T2 | UI | Use the real office renderer for 20 working colleagues, simultaneous arrivals, departures, and new arrivals | Browser | Distinct suitable desks are used and released without overlap |
| T3 | UI | Move colleagues into Fika and the meeting room through actual activity updates | Browser | Available seats are used, directions agree with furniture, and full rooms follow the accepted capacity rule |

##### Verification Results

| Label | Observed At | Environment | Result | Evidence |
| --- | --- | --- | --- | --- |
| T1 | Not run | Browser | Pending | none |
| T2 | Not run | Browser | Pending | none |
| T3 | Not run | Browser | Pending | none |

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
