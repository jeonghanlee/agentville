# AgentVille

A self-hosted, read-only virtual office for AI coding agents. Each host runs a Collector that observes local Claude Code and Codex sessions; one host runs HQ, which keeps the current state and shows it in a browser as an office floor.

![Virtual office](images/office.png)

AgentVille observes only. It never starts, resumes, answers, or interrupts an agent, and never modifies agent configuration. Prompts, commands, file paths, and tool arguments never leave the host.

| Part | Runs on | Role |
|---|---|---|
| Collector | Every host with agents (a Branch) | Watches local Claude Code and Codex sessions and reports their state. |
| HQ | One host | Stores the state of all Branches and serves the office page. |
| Browser | Anywhere | Shows the office, dashboard, colleagues, projects, timeline, and Branches. |

| Chapter | Content |
|---|---|
| [Installation](install.md) | Requirements, install, services, connecting other hosts, upgrade, removal. |
| [Configuration](configuration.md) | The Collector configuration file. |
| [Using the Office](using.md) | Rooms, states, views, and settings. |
| [Data and Security](data.md) | What is sent to HQ and what never is. |

Design and protocol specifications for developers are in the repository: [docs/architecture.md](https://github.com/jeonghanlee/agentville/blob/master/docs/architecture.md), [docs/protocol.md](https://github.com/jeonghanlee/agentville/blob/master/docs/protocol.md).

Source: [github.com/jeonghanlee/agentville](https://github.com/jeonghanlee/agentville). License: Apache License 2.0.
