# Using the Office

## Scope

This document covers the office page served by HQ: places, states, views, and settings.

**Out of scope:** how the Collector decides states (docs/architecture.md in the repository).

Open HQ in a browser, for example `http://127.0.0.1:8470/`. With a viewer token, open `.../#token=<viewer token>` once; the page keeps the token for the browser session. `/?demo=1` shows fictional colleagues without connecting to HQ; the screenshots below are taken in that mode.

## Virtual office

![Virtual office](images/office.png)

One floor per Branch. The Branch selector at the top of the office card switches Branches; the clock and window light follow the Branch's time zone.

| Place | Who is there |
|---|---|
| Project room | Colleagues working in that repository. The room name is the repository; the sublabel reads "repository". |
| Common Office | Colleagues working outside any repository. |
| Lounge (Fika) | Colleagues idle for an hour or more, with the default thresholds; each Branch can set its own ([Configuration](configuration.md)). |
| Infirmary | Colleagues in `Error`. |

A room shows a fixed number of desks; more colleagues than desks appear as "+N". Two project rooms fit on one floor; the arrows beside the room tabs show the next ones.

Each colleague wears a provider badge (`CL` Claude, `CX` Codex). Contractors (subagents) stand beside their colleague in a yellow hard hat with their own provider badge.

## Activity states

| Label | 한국어 | Shown as |
|---|---|---|
| Working | 작업 중 | Typing and using the mouse. |
| Thinking | 생각 중 | Thought bubble. Not produced from current provider signals, so it appears only in demo data (`/?demo=1`), as in the screenshots. |
| Waiting | 대기 | Raised hand and "!". The agent waits for a person's answer or approval. |
| Idle | 유휴 | At the desk; with the default thresholds, after 5 minutes on the phone, after 30 minutes dozing, after an hour in the Lounge. The thresholds are set per Branch ([Configuration](configuration.md)). |
| Closed | 닫힘 | A short check mark when a turn ends. |
| Error | 오류 | In the Infirmary. |
| Limited | 한도 | Screen off and a clock; the detail shows when the usage limit resets. |
| Not measured | 재지 못함 | Dimmed with "?". The state could not be determined. |

A Codex run that does not use the Codex app-server daemon (e.g. `codex exec`) is observed from its rollout file only, with low confidence: it never shows Waiting, shows Not measured until its next turn or tool when it was already running at Collector start, and goes off duty 30 minutes after its rollout was last written.

![Lounge](images/lounge.png)

In the Lounge, colleagues drink, read, and talk to each other with picture bubbles. This is decoration only; it shows no agent data.

## Presence

| Label | 한국어 | Meaning |
|---|---|---|
| On duty | 출근 | A provider process or thread is running (for a Codex run outside the app-server daemon: its rollout was written in the last 30 minutes). |
| Off duty | 퇴근 | It ended. |
| On leave | 휴가 | Off duty for seven days (default threshold, set per Branch). |

## Colleague details

![Colleague details](images/detail.png)

Select a colleague in the office or in the list on the right. The detail shows status, condition, tool name, recent tool count (tools started in the last 5 minutes, falling to 0 without new tools), room and Branch, Contractors, and the last observed time. Conditions are set by model settings: study-mode (high effort), extra-coffee, light (low effort), or normal.

## Other views

![Dashboard](images/dashboard.png)

| View | Content |
|---|---|
| Dashboard | Counts across all Branches: on duty, waiting, errors, Branches, and a table of colleagues. |
| Colleagues | Every colleague with Branch, room, presence, activity, tool, condition, workload, and time in state. Idle colleagues show the stage of the Idle state: Idle, Phone (휴대폰), Dozing (조는 중), or Fika (휴게실). |
| Projects | One card per repository with colleagues on duty and Branches. |
| Timeline | Changes observed while the page is open. |
| Branches | Each Branch, whether it is reporting, and its last report time. |

The search field filters colleagues and projects; the state chips above the office filter by activity.

## When data is not fresh

![Unverified](images/unverified.png)

- When the page loses HQ, it shows "Not connected to HQ" and reconnects by itself.
- When a Branch stops reporting, its colleagues keep their last observed place and state, dimmed and marked "?" (unverified).
- After HQ restarts, a Branch shows "Waiting for Branch report" until its Collector sends again (up to about a minute).

## Settings

![Settings](images/settings.png)

| Setting | Effect |
|---|---|
| Language | English or 한국어. Names reported by Branches are not translated. |
| Show colleague names | Keeps name labels visible in the office. |
| Reduce motion | Stops animations. |
| Window light | Branch time, or a fixed time of day. |
| Browser notifications | Notifies when a colleague starts waiting or has an error, and when a Branch stops or resumes reporting. Only while the page is open in a browser tab. Needs HTTPS or localhost and the browser's permission; off by default. |
| Demo data | Shown in demo mode (`/?demo=1`): fictional colleagues, HQ data unchanged. "Open live data" returns to HQ. |
