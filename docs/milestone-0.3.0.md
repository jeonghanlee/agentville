# Observation Coverage for 0.3.0

Release line: 0.3.0
Milestone index: 0.3.0
Canonical path: `docs/milestone-0.3.0.md`
Canonical branch or ref: `master`
Git upstream: origin/master
Remote tracker: none

Next session entry point: AgentVille 0.3.0 is published at https://github.com/jeonghanlee/agentville/releases/tag/0.3.0. Verify the published-tag install.sh path after the released-object storage preflight, record closure, and continue with docs/milestone-0.4.0.md M1. The immutable release candidate remains 2f9fb6b73224bd1f8612b5be74bce5c87b8f7dcf; later checkpoint commits are verification records only.

## Scope

This document tracks child-process Contractors, Antigravity observation, and remote Collector operation from the 0.2.0 baseline.

Out of scope: 0.4.0 features, release publication, changes to running services, and deployment of this checkout.

## Milestone

### Work

| ID | Work unit | Type | Status | Ready | Deps | Done when / Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| M1 | Child-process Contractors | Milestone | Complete | No | D1, D2, G1 | Process descendants are Contractors without duplicate colleagues; [detail](#m1---child-process-contractors) |
| M2 | Antigravity Adapter | Milestone | Complete | No | M1, D1 | Live Antigravity sessions report presence and observable activity; [detail](#m2---antigravity-adapter) |
| M3 | Remote development environments | Milestone | Complete | No | M2, D1 | SSH and container procedures preserve identity and reach HQ securely; [detail](#m3---remote-development-environments) |
| G1 | Late parent observation policy | External gate | Complete | No | | D2 selects later reclassification while preserving the former Employee record; [detail](#g1---late-parent-observation-policy) |
| M4 | Release 0.3.0 | Milestone | In progress | No | M1, M2, M3, G2 | Reviewed candidate is tagged, published, installed, and verified; [detail](#m4---release-030) |
| G2 | Git execution authority | External gate | Complete | No | | Owner authorizes each exact Git operation before execution; [detail](#g2---git-execution-authority) |

### Decisions

| ID | Decision | Decision Date |
| --- | --- | --- |
| D1 | Implement M1, M2, then M3 on feature/0.3.0 from Release 0.2.0. | 2026-10-22 |
| D2 | When a process-backed parent is observed later, end the child's independent Employee shift, preserve its ID and history as off duty, and continue its current activity and descendants as Contractors of the parent's root Employee. Keep established parent assignments fixed. | 2026-10-22 |

### Milestone Details

#### M1 - Child-process Contractors

Origin: 0.3.0 / M1
Identity History: none
GitHub Issue: none
Status: Complete

##### Summary

Identify agent CLIs launched by another observed agent as Contractors of the parent's shift.

##### Scope

Extend Claude and Codex observation with Linux process ancestry. Preserve existing in-process Contractors and the provider-neutral protocol. Cover S05 and the reported inaccessible-file-descriptor and Collector-restart cases.

Out of scope: linking independent invocations without process ancestry, and cross-host process ancestry.

##### Completion Criteria

- A child CLI appears once as a Contractor and never simultaneously as an independent colleague.
- The Contractor ends when its process or parent shift ends; PID reuse does not join unrelated processes.
- Unreadable process file descriptors do not silently defeat supported process matching.
- At Collector startup, a completed codex exec rollout does not create an on-duty colleague merely because its mtime is recent.
- Real adapters, Judge, and protocol validation run together using shipped fixtures.

##### Dependencies And Decisions

- D1 sets work ordering, not a runtime dependency.
- G1 is complete through D2. The owner selected and authorized late-parent reclassification on 2026-10-22; M1 resumes as In progress. Existing identity and session history remain on the off-duty Employee record.

##### Implementation Plan

Plan Status: accepted
Plan Acceptance: 2026-10-22, owner accepted the implementation and verification plan, including D2 by selecting option 1.
Implementation Authorization: 2026-10-22, owner directed implementation and selected option 1 for D2.
Superseded Plan Artifacts: none

1. Add a shared Linux process reader under `packages/agentville/collector/`: read PID, parent PID, command name, start ticks, and working directory; exclude zombies and validate lifetime identity before using a match.
2. Extend Claude start observations with process identity. Associate Codex rollouts with codex processes by open file descriptors; when descriptors are unreadable, accept only an unambiguous command-name, working-directory, and process/rollout-start-time match. Scan file descriptors only for codex processes.
3. Collect all adapters' observations for one tick before assigning Employees in `main.py`. Resolve the nearest observed ancestor through intermediate shell processes, order parents before children, and route a child shift into the existing Contractor model in `judge.py` with origin `child_process`. Recheck independent process-backed shifts after parent discovery: preserve the prior Employee ID and history as off duty, move current activity and descendants to the parent's root Employee, and then keep established ownership fixed. End descendants with the parent.
4. Keep internal process identity and paths on the Branch. Use the existing `child_process` protocol value and validate all generated messages against `protocol-v1.schema.json`.
5. In Codex rollout discovery, record initial file versions. A rollout present at attach without a matching live process cannot start a shift until its file changes. Preserve rollout-only observation after a fresh write, bounded by the existing inactivity window; process-backed shifts end on process exit.
6. Ship S05 process-tree and provider-log fixtures, replay them through actual adapters, Collector, Judge, and protocol validation, and run real-process tests for denied descriptor access, nested ancestry, PID reuse, parent exit, and Collector restart.

##### Test Plan

| Label | Layer | Method | Environment | Expected Result |
| --- | --- | --- | --- | --- |
| T1 | Integration | Claude and Codex S05 fixtures through actual adapters, Collector, and protocol validation | Linux, Python 3.12+ | One parent colleague and child Contractor, with correct end events |
| T2 | Integration | Real child processes, including denied fd access and PID lifetime checks | Linux /proc | Correct ownership or explicit unknown evidence; no unrelated parent |
| T3 | Regression | Restart Collector with a completed child rollout, then append a fresh event | Linux, synthetic rollout | Old child remains off duty until fresh evidence establishes activity |
| T4 | Integration | Delay the parent session file while a real child process is working; vary Adapter order, restart the Collector, and use the shipped process tree for descendants | Linux, shipped S05 worker and fixture | Child activity becomes a Contractor; its former Employee ID and history remain off duty; descendants migrate and end correctly |

##### Verification Results

| Label | Observed At | Environment | Result | Evidence |
| --- | --- | --- | --- | --- |
| T1 | 2026-10-22 21:48:11 UTC | Linux, Python 3.13.5 | Passed | /tmp/agentville-030-R1-full.xml; actual Claude and Codex Adapters, Collector, JSONL Sender, and protocol validation with shipped S05 inputs. |
| T2 | 2026-10-22 21:48:11 UTC | Linux procfs and synthetic procfs boundary | Passed | /tmp/agentville-030-R1-full.xml; actual processes with accessible and denied descriptors; intermediate shell ancestry, nested child Contractors, ambiguous matching, truncated process names, and changed parent start ticks use the shipped process fixture. |
| T3 | 2026-10-22 21:48:11 UTC | Linux, actual Collector restart with roster and seq files | Passed | /tmp/agentville-030-R1-full.xml; completed child rollout creates no colleague on restart; a fresh write starts a new low-confidence rollout-only shift. |
| T4 | 2026-10-22 21:48:11 UTC | Linux, actual processes and full Collector path; synthetic procfs boundary for nested descendants | Passed | /tmp/agentville-030-R1-full.xml; both Adapter orders preserve the prior Employee ID and sessions as off duty, transfer active tool state, survive Collector restart, and end on child exit. Nested process Contractors migrate to the root and end on parent PID reuse. The Judge unit case also verifies in-process Contractor migration and subsequent status updates. |

##### Closure Evidence

- D2 is implemented and T1-T4 passed. The full pytest run recorded 290 passed, zero failures, zero errors, and zero skips. The pre-fix failure remains in `/tmp/agentville-030-pytest.2FpfDt/results.xml`. Self-review is accepted. Observed 2026-10-22 23:11:34 UTC: implementation commit `cc8168af4eae02ce05c921c9ccf191a9b0e62723` is an ancestor of fetched `origin/feature/0.3.0` at `42236e561ed5614a6c6e9da7d8cee6cccad4a981`. A Git comparison found no differences in packages, tests, pyproject.toml, architecture, or remote procedures. The 60 package and version files match the retained Docker context. GitHub test run [39864177993](https://github.com/jeonghanlee/agentville/actions/runs/39864177993) completed successfully for Python 3.12, Python 3.13, and the actual install.sh path. Required local checks and accepted self-review are recorded above; no external tracker issue exists.

#### M2 - Antigravity Adapter

Origin: 0.3.0 / M2
Identity History: none
GitHub Issue: none
Status: Complete

##### Summary

Observe Antigravity CLI presence and work activity from sources available on the host.

##### Scope

Inspect live agy presence locks, process lifetime, and transcript structure. Add account configuration, an Adapter, synthetic fixtures, and provider rendering. Derive supported states from observed evidence. Clear completed tool names and document the overlap between ~/.gemini and Gemini CLI.

Out of scope: inferred thinking, waiting or usage-limit signals without observed evidence, and starting or controlling user sessions.

##### Completion Criteria

- Live presence and exit follow the owning process and lock, including restart and stale-file cases.
- Supported activity states match observed source records and agree across documents.
- Completed tools do not remain on colleague details.
- Provider configuration, protocol, and UI support Antigravity without exposing prompts, paths, account identities, or tool arguments.
- Shipped synthetic fixtures exercise the real Adapter and Collector path.

##### Dependencies And Decisions

- M1 precedes M2 by D1; this is work ordering.
- Live agy is available on the development host; inspect it without controlling its sessions.
- R1 correction was accepted and authorized on 2026-10-22 by the owner's selection of option 1. Remember content-free activity fingerprints throughout a shift, including complete history at attach, to prevent old records from changing state or increasing workload after rotation or truncation. Verify both history replay and fresh appended records through the real Collector.

##### Implementation Plan

Plan Status: accepted
Plan Acceptance: 2026-10-22, owner accepted the implementation and verification plan, including correction option 1 for R1.
Implementation Authorization: 2026-10-22, owner directed implementation and selected correction option 1 for R1.
Superseded Plan Artifacts: none

1. Resolve held `presence/<conversation-id>.lock` files to their owning agy process through `/proc/locks`, verify PID and start ticks, and use the owner's current working directory for Project identity. A stale unlocked file is not presence.
2. Add `adapters/antigravity.py`, using `JsonlTail` on `brain/<conversation-id>/.system_generated/logs/transcript.jsonl`. Parse only activity fields and tool names. At attach, fingerprint complete historical activity records without emitting them and seed current activity from the tail. Retain activity fingerprints for the shift lifetime across rotation and truncation, skip repeated records, and still process fresh appended records. Never retain content or tool arguments in the fingerprint identity, or send private identifiers.
3. Confirm state transitions against live agy before specifying their mapping: observed record types include `USER_INPUT`, `PLANNER_RESPONSE`, `GENERIC`, `CHECKPOINT`, `SYSTEM_MESSAGE`, and `ERROR_MESSAGE`; observed statuses are `RUNNING`, `DONE`, and `ERROR`. Distinguish model completion, tool completion, and agent failure instead of mapping every `DONE` or `ERROR` to the same activity.
4. Extend `config.py` and `build_adapters` with Antigravity account homes, require the `antigravity-cli` subtree before discovering a Gemini home automatically, and cover provider values in protocol validation and Web UI badges.
5. Ship synthetic Antigravity fixtures based on the observed field structure. Verify presence, active work, completion, error, stale-lock behavior, transcript rotation, and removal of completed tool names through the actual Adapter and Collector.
6. Update architecture, configuration, fixture, and usage documents with the states actually emitted. Document the `~/.gemini` overlap with Gemini CLI and any observation limitations.

##### Test Plan

| Label | Layer | Method | Environment | Expected Result |
| --- | --- | --- | --- | --- |
| T1 | Observation | Inspect agy process, lock ownership, and source field names | Live Linux host | Documented signals have direct evidence |
| T2 | Integration | Synthetic Antigravity fixtures through actual Adapter, Collector, and protocol validation | Linux, Python 3.12+ | Presence and supported states match fixtures |
| T3 | Regression | Complete a tool, truncate or rotate a transcript, and end its process | Linux, synthetic fixtures | No stale tool, history replay, or phantom shift |

##### Verification Results

| Label | Observed At | Environment | Result | Evidence |
| --- | --- | --- | --- | --- |
| T1 | 2026-10-22 21:12:55 UTC | Live Linux host, agy 1.4.5 | Passed | `/tmp/agentville-030-agy-epwmvww1/receipt.json`: actual Adapter observed one live shift, seeded idle, and emitted no new shift on its second poll. Native lock ownership and process start ticks matched. Transcript field structure was inspected without retaining content; tool and error transitions are synthetic-fixture evidence, not a live-session-control claim. |
| T2 | 2026-10-22 21:48:11 UTC | Linux, Python 3.13.5 | Passed | /tmp/agentville-030-R1-full.xml; actual kernel lock, process, Adapter, Collector, Judge, JSONL Sender, and schema validation consume generated agy 1.4.5 records. |
| T3 | 2026-10-22 21:48:11 UTC | Linux, shipped agy fixture, actual kernel lock, Adapter, and Collector | Passed | `/tmp/agentville-030-R1-full.xml`; fresh history, existing history, and history beyond the 256 KiB tail window preserve state and workload across file replacement and truncation. A fresh appended tool is counted once and finishes normally. The two original cases failed on the pre-fix source in `/tmp/agentville-030-R1-before.xml`; the earlier workload 1-to-2 reproduction remains in `/tmp/agentville-030-review-extra-with-rotation.xml`. |

##### Review Results

Review target: current 0.3.0 changes on `feature/0.3.0`, M1-M3 implementation, tests, and documentation. Office expansion implementation and deployment are excluded. No earlier formal passes for this reconstructed working tree were available.

- Available pass 1, first-person: three deliberate choices, one previously missed late-parent ordering case now corrected by D2, no loose ends or sentence corrections.
- Available pass 2, third-person: one minor finding, R1, against M2 / T3. The pre-fix Adapter remembered only active tools, so replaying a finished step emitted `tool.started` again; the original rotation test expected that duplicate. The owner accepted correction option 1 on 2026-10-22. R1 is resolved by shift-lifetime hashes of activity fields, including historical records at attach, and a regression that failed before the correction and passes afterward.
- Additional real-path checks for late-parent classification through actual HTTP and HQ, and concurrent Antigravity tool completion, passed. The additional three-case run has two passes and one failure. Source: `/tmp/agentville_030_review_checks.py`; result: `/tmp/agentville-030-review-extra-with-rotation.xml`.
- Available pass 3, third-person: no additional findings. The corrected 290-case base suite and 18 Docker/SSH assertions pass. `/tmp/agentville-030-R1-review.xml` records three passing additional real-path checks, including preservation of state and workload when replayed content and tool arguments differ. The current source matches the retained Docker build context, excluding Python caches.
- Available pass 4, second-person: no findings from the remote operator's seat. The current remote procedure, configuration, changed architecture and protocol descriptions, fixture instructions, and canonical evidence were checked against the real executions; mdBook built successfully on 2026-10-22 at 21:50 UTC. This was self-review, with no independent reviewer or delegated pass.
- The loop is closed with no open findings. Recorded totals: four available passes, all direct; one first-person, two third-person, one second-person. The initial third-person minor R1 is resolved; no must-fix, info, hygiene, or out-of-scope findings were recorded. Termination: no finding above the floor.

##### Closure Evidence

- Native presence, synthetic activity, transcript-history deduplication, and subsequent fresh records passed. R1 is resolved and self-review is accepted. Observed 2026-10-22 23:11:34 UTC: implementation commit `cc8168af4eae02ce05c921c9ccf191a9b0e62723` is an ancestor of fetched `origin/feature/0.3.0` at `42236e561ed5614a6c6e9da7d8cee6cccad4a981`. A Git comparison found no differences in packages, tests, pyproject.toml, architecture, or remote procedures. The 60 package and version files match the retained Docker context. GitHub test run [39864177993](https://github.com/jeonghanlee/agentville/actions/runs/39864177993) completed successfully for Python 3.12, Python 3.13, and the actual install.sh path. Required local checks and accepted self-review are recorded above; no external tracker issue exists.

#### M3 - Remote Development Environments

Origin: 0.3.0 / M3
Identity History: none
GitHub Issue: none
Status: Complete

##### Summary

Provide SSH and container Collector operation with durable Branch identity and an explicit HQ network boundary.

##### Scope

Document persistent configuration, sequence, and roster storage; tunnel and direct-HQ networking; Collector restart; and container volume ownership. Detect conflicting messages from cloned host.id and seq state, distinguish exact retries, and disambiguate Branch aliases in colleague details and work logs.

Out of scope: changing host.id during normal startup, automatic merging of two Collectors, and deployment to user services.

##### Completion Criteria

- Container rebuilds retain Branch and colleague IDs when their documented storage persists.
- Two Collectors sharing host.id produce the documented warning even when their seq numbers coincide and message content differs; exact retries remain duplicates.
- Container procedures explain SSH-host loopback versus container loopback, working connection methods, token requirements, ownership, and restart.
- Documented token settings reject unauthorized ingest; loopback requests bypass environment proxies as documented.
- Equal Branch aliases remain distinguishable in colleague details and work logs.
- Each verification distinguishes executed behavior from unavailable infrastructure.

##### Dependencies And Decisions

- M2 precedes M3 by D1; this is work ordering.

##### Implementation Plan

Plan Status: accepted
Plan Acceptance: 2026-10-22, owner accepted the implementation and verification plan.
Implementation Authorization: 2026-10-22, owner directed implementation of this plan.
Superseded Plan Artifacts: none

1. In `hq/store.py`, compare all stored envelope fields and decoded payload when `(branch_id, seq)` already exists, including snapshot duplicates. Preserve exact retry behavior; detect conflicting content and report a possible shared host.id without logging message contents or credentials. Preserve documented sequence-reset and clock-reset behavior.
2. Cover copied Collector configuration and sequence state against real HQ ingest, both coincident sequence numbers and later conflicting activity; verify exact retries do not raise a warning. Write the exact diagnostic and recovery instructions in the installation documentation.
3. Document persistent config and state paths, one Collector per identity, and a new host.id for an independently cloned environment. Retain both config and roster/seq volumes during container rebuilds and set volume ownership for the actual container UID/GID.
4. Provide separate host-network and Docker-host-gateway connection procedures. A reverse SSH tunnel bound to the SSH host's loopback is reachable from a host-network container; the gateway method requires an explicitly reachable bind, appropriate SSH forwarding policy, HQ authentication, and limited network access. Plain non-loopback HTTP cannot carry a Collector token under the existing Sender policy; verify and document the applicable HTTPS or tunnel boundary.
5. Include start, stop, and restart for a foreground or nohup Collector, verify PID identity before stopping it, and show proxy bypass settings. Execute procedures in isolated SSH and Docker environments without changing the installed services.
6. Reuse a shared Branch-display helper in Web UI colleague details and work logs so equal aliases include the full distinguishing Branch ID. Exercise both views with duplicate aliases.

##### Test Plan

| Label | Layer | Method | Environment | Expected Result |
| --- | --- | --- | --- | --- |
| T1 | Integration | Run Collectors with copied identity and sequence state against real HQ ingest | Linux, isolated database | Conflicting content warns; identical retries do not |
| T2 | Integration | Rebuild container with persistent config and state volumes | Docker | Branch and colleague IDs persist; writable ownership |
| T3 | Integration | Follow tunnel, token, proxy, and Collector-restart procedures | SSH and Docker test environment | HQ is reachable only through the intended authenticated boundary |
| T4 | UI | Render equal-alias Branches in colleague details and work logs | Browser or existing UI test harness | Branch IDs distinguish equal aliases |

##### Verification Results

| Label | Observed At | Environment | Result | Evidence |
| --- | --- | --- | --- | --- |
| T1 | 2026-10-22 21:48:11 UTC | Real HQ HTTP ingest and actual Collectors | Passed | /tmp/agentville-030-R1-full.xml; copied identity and coincident seq with different snapshot payload warns, exact stored-envelope replay does not, and conflicting heartbeat content warns. |
| T2 | 2026-10-22 | Docker 29.9.1, installed Collector, persistent named volumes | Passed | `/tmp/agentville-030-system-liatpmu9/results.json` and `commands.jsonl`; fresh root-owned volumes are reassigned, two recreated containers retain host.id and colleague ID, and the actual Git resolver identifies the synthetic remote Project. |
| T3 | 2026-10-22 | Isolated SSH server, host-network and bridge containers, real HQ | Passed | `/tmp/agentville-030-system-liatpmu9/results.json`: all 18 assertions passed, including reverse SSH delivery, two nohup runs, process/start-time receipts, bridge-loopback refusal, and host-gateway SSH delivery. /tmp/agentville-030-R1-full.xml also verifies token rejection and loopback proxy bypass. |
| T4 | 2026-10-22 21:48:11 UTC | Actual Chromium and HQ, 1440px and 720px | Passed | /tmp/agentville-030-R1-full.xml; both Branch IDs appear in colleague detail and work-log headings; AG badge renders with no page errors. Screenshots were inspected. |

##### Closure Evidence

- HTTP, Docker, SSH, browser, and mdBook checks ran against the working tree. `packages/` and `pyproject.toml` match `/tmp/agentville-030-system-liatpmu9/context/` byte for byte, excluding Python caches. Test containers are stopped; generated images, volumes, and private evidence remain. Self-review is accepted. Observed 2026-10-22 23:11:34 UTC: implementation commit `cc8168af4eae02ce05c921c9ccf191a9b0e62723` is an ancestor of fetched `origin/feature/0.3.0` at `42236e561ed5614a6c6e9da7d8cee6cccad4a981`. A Git comparison found no differences in packages, tests, pyproject.toml, architecture, or remote procedures. The 60 package and version files match the retained Docker context. GitHub test run [39864177993](https://github.com/jeonghanlee/agentville/actions/runs/39864177993) completed successfully for Python 3.12, Python 3.13, and the actual install.sh path. Required local checks and accepted self-review are recorded above; no external tracker issue exists.

#### G1 - Late Parent Observation Policy

Origin: 0.3.0 / G1
GitHub Issue: none
Status: Complete

##### Summary

The owner selected option 1 on 2026-10-22: reclassify after parent evidence arrives while retaining the prior Employee ID and history as off duty. D2 records the accepted and authorized behavior for M1. The regression now passes in both Adapter orders; M1 / T4 records the executed evidence.

##### Completion Criteria

- The owner selects the behavior, and the canonical implementation and verification plan records that dated decision and authority.

##### Verification Results

| Observed At | Result | Evidence |
| --- | --- | --- |
| 2026-10-22 | Complete | Owner selected option 1; D2 records the decision and M1 records plan acceptance and implementation authority. |

##### Closure Evidence

- D2, Decision Date 2026-10-22. Owner selected option 1.

#### M4 - Release 0.3.0

Origin: 0.3.0 / M4
Identity History: none
GitHub Issue: none
Status: In progress

##### Summary

Prepare and publish AgentVille 0.3.0 from the reviewed observation changes.

##### Scope

Implementation landing, CHANGELOG, version-only change, candidate verification, annotated tag, existing GitHub release workflow, and released-install verification.

Out of scope: deploying to existing user services, implementing 0.4.0, and changing the existing publication workflow.

##### Completion Criteria

- Version metadata, installed CLI versions, CHANGELOG, tag, and GitHub Release agree on 0.3.0.
- All required candidate and released-object checks pass with retained evidence.
- M1-M3 have landing evidence and the next entry points at the 0.4.0 document.

##### Dependencies And Decisions

- M1-M3 are Complete with local checks, accepted self-review, fetched-origin landing evidence, and successful Python 3.12/3.13 and installer CI. Release publication remains pending.
- G2 completed on 2026-10-22 after the owner delegated the previewed commit, master Push, Release, and single-tag Push scopes. M4 resumes as In progress.
- The owner requested formal release, master integration, and subsequent 0.4.0 work on 2026-10-22, and selected fast-forward integration. Release-plan acceptance and implementation authority are recorded below. The earlier implementation and CHANGELOG commit delegation and initial branch push were bounded and consumed; later Git actions need their matching scopes.
- Public REST observation on 2026-10-22 found releases 0.1.0 and 0.2.0 and no remote milestones. Git SSH observation found master at `39f1d0cb3c7c8011ffe05fd5f934db75d5e2131b` and no 0.3.0 tag. Local gh authentication returned 401; Git SSH reads succeeded. Recheck live state before execution.
- `.github/workflows/release.yml` creates the Release when a numeric tag is pushed. Do not also create a duplicate Release manually. The workflow's extraction consumes the prepared CHANGELOG section.

##### Implementation Plan

Plan Status: accepted
Plan Acceptance: 2026-10-22, owner requested the formal release followed by 0.4.0 and selected fast-forward master integration.
Implementation Authorization: 2026-10-22, owner requested this release plan; individual Git execution scopes remain separately required.
Superseded Plan Artifacts: none

1. Preserve the landed implementation and separate CHANGELOG commits. Commit the accepted release plan and observed pre-change evidence before the version change.
2. After the pre-bump tree is otherwise clean, change only `pyproject.toml` version from 0.2.0 to 0.3.0 and commit it separately.
3. Verify candidate versions, the full suite, Python 3.12/3.13 CI, and installation of the exact candidate through install.sh in an isolated environment. Record and commit readiness evidence under separate authority.
4. Resolve and retain the immutable candidate. Fast-forward master only if possible, create an annotated 0.3.0 tag at that exact candidate, and perform only separately authorized branch and single-tag pushes. Record each observed action in a separately authorized checkpoint commit before the next dependent action. Checkpoint commits do not change the retained tag target. Observe the existing workflow's published Release.
5. Check released objects and run install.sh against the published tag on a clean equivalent host after the storage preflight in the release-cycle closing procedure. Record closure without rewriting the tag; retain `docs/milestone-0.4.0.md` for the next line.

##### Test Plan

See Release Verification Plan; this final release detail has no local T labels.

##### Verification Results

See Release Verification Results. Existing feature checks remain in M1-M3.

##### Integrated Verification

| Source Check | Re-run Trigger | Shared Surface | Release Verification Label | Expected Result | Result Evidence |
| --- | --- | --- | --- | --- | --- |
| M1 / T1-T4, M2 / T2-T3, M3 / T1-T4 | Version change or any package, schema, UI, or dependency change | Combined installed package | Release Verification 4 | Candidate suite and environment checks pass | Pass; Release Verification 4 records local checks and exact-candidate supported-Python and installer CI |

##### Production Environment Tests

| Release Verification Label | Timing | System | Version | Architecture | Deployment Path | Method | Expected Result | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Release Verification 5 | post-change | Fresh isolated Linux container, user 1000 | 0.3.0 candidate | x86_64 | /home/dev/.local/opt/agentville in the fresh container | Actual install.sh --hq --no-start on immutable local candidate; installed CLI and real HQ delivery checks | Both commands run at 0.3.0 and reporting succeeds | /tmp/agentville-030-install-wngt1l64/receipt.json; Pass |
| Release Verification 7 | post-release | Clean production-equivalent Linux host | Published 0.3.0 | Record actual architecture | Fresh dedicated home | Complete released-object storage preflight, install actual published tag through install.sh, and verify delivery to isolated HQ | Released installation and delivery succeed | Pending |

##### Version Changes

| Field | File | Before | Planned After | Pre-check | Pre-check Label | Post-check | Post-check Label |
| --- | --- | --- | --- | --- | --- | --- | --- |
| project.version | pyproject.toml | 0.2.0 | 0.3.0 | Parse TOML and inspect the otherwise clean pre-bump tree | Release Verification 2 | Build/install candidate and check package metadata plus both --version entry points | Release Verification 3 |

##### Release Execution

| Step | Action | Authorization | Expected Result | Evidence |
| --- | --- | --- | --- | --- |
| 1 | Commit reviewed implementation and CHANGELOG separately | Owner delegated the two commits and initial push on 2026-10-22 | Named commits preserve reviewed bytes | cc8168af4eae02ce05c921c9ccf191a9b0e62723 and 42236e561ed5614a6c6e9da7d8cee6cccad4a981; fetched origin/feature/0.3.0 matches HEAD; CI run 39864177993 succeeded |
| 2 | Commit version-only 0.3.0 change and readiness evidence separately | Owner delegated version and verification-record commits on 2026-10-22 | Candidate checks identify immutable commit | Pre-change plan/evidence: 8a01d7bc5794e25504283694a20359b6026ab1fb. Version-only commit: b73739a4b3ce5d47177d788945769e3cad38d400. Retained readiness candidate and tag target: 2f9fb6b73224bd1f8612b5be74bce5c87b8f7dcf. This verification-only checkpoint records its observed CI and does not change that target. |
| 3 | Push candidate branch and inspect test workflow | Owner delegated one candidate-branch push on 2026-10-22; executed | Exact candidate passes supported Python CI | Observed 2026-10-22T23:39:57.659785+00:00: fetched origin/feature/0.3.0 equals 2f9fb6b73224bd1f8612b5be74bce5c87b8f7dcf; committed package, test, version, and milestone paths match. [Run 39873163675](https://github.com/jeonghanlee/agentville/actions/runs/39873163675) succeeded for pytest (3.12), pytest (3.13), and install. |
| 4 | Fast-forward master with the retained candidate and verification-only checkpoint | Owner delegated the previewed Release sequence on 2026-10-22 | No history rewrite or unresolved merge | Observed 2026-10-22T23:48:40.533492+00:00: git merge --ff-only a561b5ed5542219af5e430f64bd8d3fe97e86ce3 moved local master from 39f1d0cb3c7c8011ffe05fd5f934db75d5e2131b to that exact commit; no merge commit or source changes. |
| 5 | Create annotated refs/tags/0.3.0 at the resolved candidate | Owner delegated the previewed Release sequence on 2026-10-22 | Immutable annotated tag | Observed 2026-10-22T23:50:03.284585+00:00: annotated tag object 9548c089f57b801d2bcf2596d599cc7c26910505 peels to retained candidate 2f9fb6b73224bd1f8612b5be74bce5c87b8f7dcf; title AgentVille 0.3.0. Not yet pushed. |
| 6 | Push master and the one tag; tag push triggers release.yml | Owner separately delegated master Push and single-tag Push on 2026-10-22 | Remote objects match local accepted objects; Release is created once | Master Push observed 2026-10-22T23:51:39.070757+00:00: fetched origin/master equals ce94b4d87dcf5b8b55f533da16af3abe064ee412 and contains candidate 2f9fb6b73224bd1f8612b5be74bce5c87b8f7dcf. Single-tag Push and Release observation completed: remote tag object 9548c089f57b801d2bcf2596d599cc7c26910505 peels to retained candidate 2f9fb6b73224bd1f8612b5be74bce5c87b8f7dcf. Release 421311845 is published, non-draft, non-prerelease, and latest; release workflow 39874566624 succeeded. |
| 7 | Record released checks, M1-M4 closure, and next-line entry point | Commit scope or user execution | Closure evidence is committed after publication | Pending |

##### Release Verification Plan

| Label | Layer | Timing | Method | Environment | Expected Result | Evidence Target |
| --- | --- | --- | --- | --- | --- | --- |
| Release Verification 1 | Local | pre-change | Reconcile M1-M3 evidence, changed paths, and CHANGELOG scope | Current working tree | Source and recorded checks agree | Canonical evidence and source comparison |
| Release Verification 2 | Local | pre-change | Parse version and verify pre-bump commit boundary | Git and TOML | Version is 0.2.0; prior changes committed | Commit identity and clean status |
| Release Verification 3 | Package | post-change | Install candidate and run both CLI --version commands | Isolated environment | Metadata and CLI versions equal 0.3.0 | Installed-command receipts |
| Release Verification 4 | Integrated | post-change | Full pytest, Docker/SSH, browser, mdBook, and Python 3.12/3.13 CI on exact candidate | Local and GitHub Actions | All required checks pass | Candidate XML, system evidence, workflow runs |
| Release Verification 5 | Installation | post-change | Actual documented install.sh path on immutable candidate | Clean isolated Linux environment | Candidate installation succeeds | Installer receipts |
| Release Verification 6 | Remote | post-release | Read tag type, peeled commit, Release identity and flags, workflow conclusion | Canonical Git remote and GitHub | Published objects identify accepted candidate | Remote object identifiers and observed metadata |
| Release Verification 7 | Installation | post-release | Storage preflight followed by actual released-tag installation and delivery | Clean equivalent host | Released install and operation succeed | Installed files, CLI output, HQ delivery |
| Release Verification 8 | Documentation | post-release | Verify canonical closure and existing 0.4.0 entry point | Committed documents | Truthful release closure and next line | Closure commit |

##### Release Verification Results

| Label | Observed At | Environment | Result | Evidence |
| --- | --- | --- | --- | --- |
| Release Verification 1 | 2026-10-22 | Working tree and prepared release files | Pass | CHANGELOG covers the implemented M1-M3 behavior. The source still matches the 290-test and 18-assertion candidate checked before release preparation. The actual release.yml note-extraction step produced a byte-identical body to `work/release-notes-0.3.0.md`; retained output: `/tmp/agentville-release-notes-m14dkxhe/notes.md`. Explicit authored-path coverage, script syntax, ShellCheck, version-patch applicability, and diff checks passed. A static scan of the 38 proposed public files found no strong credential-pattern matches. This is pre-change evidence, not versioned-candidate or publication verification. |
| Release Verification 2 | 2026-10-22 23:11:34 UTC | Git and TOML | Pass | HEAD and fetched origin/feature/0.3.0 both equal 42236e561ed5614a6c6e9da7d8cee6cccad4a981; the working tree was clean before this evidence update; pyproject.toml reports 0.2.0. This is the retained pre-change observation; the version-only commit is recorded in Release Execution. |
| Release Verification 3 | 2026-10-22T23:27:35.154471+00:00 | Fresh Python 3.13.5 virtual environment | Pass | /tmp/agentville-030-version-iZoOR6/package-receipt.json: both CLI entry points report 0.3.0; all 59 installed package files match the source later committed as b73739a4b3ce5d47177d788945769e3cad38d400. The recorded version-file SHA-256 matches that commit. |
| Release Verification 4 | 2026-10-22T23:39:57.659785+00:00 | Python 3.13.5, real Linux processes, Chromium, Docker and SSH | Pass | Local checks pass: /tmp/agentville-030-version-iZoOR6/pytest.xml records 290 passed, zero errors, failures, or skips, including 1440px and 720px browser cases. /tmp/agentville-030-system-mgriqjab/results.json records 18 passing assertions through installed Collectors and real SSH/HQ; its 60 package/version files match the committed source. mdBook and the actual release workflow version and note-extraction steps pass; /tmp/agentville-030-version-iZoOR6/workflow-receipt.json retains the workflow result. [GitHub test run 39873163675](https://github.com/jeonghanlee/agentville/actions/runs/39873163675) completed successfully for the exact retained candidate 2f9fb6b73224bd1f8612b5be74bce5c87b8f7dcf: pytest (3.12), pytest (3.13), and the actual install.sh job all succeeded. /tmp/agentville-030-version-iZoOR6/candidate-ci.json retains the live run and job observations. |
| Release Verification 5 | 2026-10-22T23:35:28.597084+00:00 | Fresh Linux x86_64 container, user 1000, Python 3.13 | Pass | /tmp/agentville-030-install-wngt1l64/receipt.json and commands.jsonl: actual install.sh --hq --no-start --ref b73739a4b3ce5d47177d788945769e3cad38d400 cloned the local candidate Git repository into an absent installation path. Both installed CLIs report 0.3.0; 59 installed package files match; the actual Collector delivered 2 messages to an isolated installed HQ, its Branch is reachable, and the web endpoint returned 200. HQ and the verification container stopped; evidence is retained. Exact retained-candidate installation is additionally confirmed by the successful install.sh job in CI run 39873163675. |
| Release Verification 6 | 2026-10-22T23:52:48.375886+00:00 | Canonical Git remote and GitHub | Pass | Remote annotated tag object 9548c089f57b801d2bcf2596d599cc7c26910505 and peeled commit 2f9fb6b73224bd1f8612b5be74bce5c87b8f7dcf match the approved local objects. [Release 0.3.0](https://github.com/jeonghanlee/agentville/releases/tag/0.3.0), ID 421311845, is published, non-draft, non-prerelease, and latest. [Release workflow 39874566624](https://github.com/jeonghanlee/agentville/actions/runs/39874566624) succeeded; its notes match the prepared body apart from surrounding blank lines. /tmp/agentville-030-version-iZoOR6/published-release.json retains the observed objects. |
| Release Verification 7 | Not run | Released installation | Pending | none |
| Release Verification 8 | Not run | Committed documents | Pending | none |

Release-preparation review: one standalone second-person self-review of the CHANGELOG, draft release plan, explicit commit paths, staging script, release notes, and unapplied version patch on 2026-10-22; no findings. This is a distinct artifact target from the four implementation review passes recorded under M2. The owner accepted the release plan and selected fast-forward integration on 2026-10-22. Version and verification-record commits plus one candidate-branch push were delegated on 2026-10-22. The owner supplied the separately previewed master integration, master Push, annotated-tag creation, single-tag Push, and verification-record Commit scopes on 2026-10-22.

##### Closure Evidence

- none

#### G2 - Git Execution Authority

Origin: 0.3.0 / G2
GitHub Issue: none
Status: Complete

##### Summary

The owner accepted the fast-forward release plan and separately delegated the previewed Commit/add, master Push, Release, and single-tag Push scopes on 2026-10-22. These bounded scopes authorize the recorded release actions; their results remain separate evidence under M4.

##### Completion Criteria

- The owner accepts the concrete release plan and supplies the applicable execution authority, separately for commits, branch pushes, and previewed release actions.

##### Verification Results

| Observed At | Result | Evidence |
| --- | --- | --- |
| 2026-10-22 | Complete | The owner supplied Commit/add, master Push, Release, and single-tag Push scopes after the exact merge and tag targets and commands were previewed. |

##### Closure Evidence

- Decision Date: 2026-10-22. Accepted fast-forward release plan and matching explicit execution scopes for the previewed commands.

## Backlog

### Work

| ID | Work unit | Type | Status | Ready | Deps | Done when / Evidence |
| --- | --- | --- | --- | --- | --- | --- |

### Backlog Details

No unassigned work.
