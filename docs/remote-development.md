# Run a remote Collector

Run the Collector beside the agents in an SSH workspace or development container, and send its observations to HQ through an authenticated connection.

## Scope

This procedure covers Collector identity, persistent container storage, SSH forwarding, and manual restart.

Out of scope: installing an SSH server, configuring Docker itself, controlling agent sessions, and observing host processes from a different container PID namespace.

## Prerequisites

- Install the Collector with Python 3.12 or later using the [installation guide](install.md).
- Configure SSH key authentication from the HQ workstation to the development host. Keep that connection open while using its tunnel.
- Configure HQ with `--no-trust-loopback`, a token for each Branch, and the viewer token as described in the installation guide. A tunnel makes connections appear local to HQ; it does not establish Branch identity.
- For containers, agents and Collector must share the process namespace and provider homes. Mount provider data only where its owner authorizes it.
- For the nohup procedure, Bash, `nohup`, `ps`, and `kill` must be available in that environment.

## Steps

1. Choose one Collector for each persistent environment. Retain its config and state directories together: `$XDG_CONFIG_HOME/agentville/` contains `host.id`, and `$XDG_STATE_HOME/agentville/` contains `seq` and `roster.json`. Defaults are `~/.config/agentville/` and `~/.local/state/agentville/`.

   A rebuild of the same environment retains both directories. An independent copy needs a different `host.id`; generate a config in an empty dedicated config directory rather than copying the original identity. Do not run two Collectors against the same state directory.

2. For Docker, create dedicated volumes before creating the development container:

   ```bash
   docker volume create <config_volume>
   docker volume create <state_volume>
   ```

   In its Docker launch options, mount the first volume at `/config` and the second at `/state`, and set these environment variables:

   ```text
   XDG_CONFIG_HOME=/config
   XDG_STATE_HOME=/state
   ```

   Fresh named volumes can belong to root. On the Docker host, assign these dedicated volumes to the Collector's UID and GID before starting it:

   ```bash
   docker exec --user 0 <container> chown -R <uid>:<gid> /config /state
   ```

   Replace `<uid>` and `<gid>` with the values inside the container, not the workstation's values. Keep both volumes when recreating the container. Run the Collector as that user.

3. On the HQ workstation, forward an unused port on the development host back to HQ:

   ```bash
   forward=127.0.0.1:<forward_port>:127.0.0.1:<hq_port>
   ssh -N -o ExitOnForwardFailure=yes -R "$forward" <user>@<dev_host>
   ```

   `<hq_port>` is HQ's loopback port on this workstation; `<forward_port>` is a free port on the SSH host. For example, forwarding port 18470 to HQ port 8470 gives `127.0.0.1:18470:127.0.0.1:8470`. `-N` keeps the connection open without starting a remote command. If a host alias has automatic backgrounding or multiplexing configured, use a separate SSH configuration for this tunnel.

   A Collector running directly on the SSH host can reach this port. A Linux container started with `--network host` shares the SSH host's network namespace and can also reach it. Host networking removes network isolation; use it only for a trusted development container.

   A bridge-network container has a separate loopback. Adding `host.docker.internal:host-gateway` does not make the host's loopback listener reachable. For this mode, add `--add-host=host.docker.internal:host-gateway` when creating the container and allow SSH to the Docker host on a reachable, restricted interface. Inside the container, open a second tunnel:

   ```bash
   forward=127.0.0.1:<forward_port>:127.0.0.1:<forward_port>
   ssh -N -o ExitOnForwardFailure=yes -L "$forward" <user>@host.docker.internal
   ```

   This connection reaches the reverse tunnel through SSH on the Docker host. Keep both SSH connections open. It needs forwarding permission on that SSH server, but no public HQ port and no `GatewayPorts` change. Restrict the SSH listener to the required interface and authenticated users.

   An alternative is direct HTTPS from the container to HQ, with a trusted certificate and Branch token. A plain HTTP gateway address cannot carry a token: the Collector rejects non-loopback HTTP with a token. Do not disable that check or expose an unauthenticated HQ to work around it.

4. In the environment running the Collector, create its config without reporting or changing its state files:

   ```bash
   agentville-collector --once --output /dev/null
   ```

   Register its generated `host.id` and token at HQ. Set `hq.url` to `http://127.0.0.1:<forward_port>` and `hq.token` to that Branch's token in its config. Keep the file mode 0600. A loopback connection bypasses environment proxies; a direct HTTPS connection follows the normal proxy settings, so set `NO_PROXY` for HQ if the environment requires a direct route.

5. In the same environment, verify one delivery:

   ```bash
   agentville-collector --once
   ```

   Check standard error and HQ's Branches view. `--once` can exit successfully after a delivery failure, so the exit status alone is insufficient. A message starting with `delivery failed:` means the Branch did not report successfully.

6. Without systemd, start the Collector from Bash in that environment and save its PID:

   ```bash
   export XDG_STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
   umask 077
   mkdir -p "$XDG_STATE_HOME/agentville"
   nohup agentville-collector > "$XDG_STATE_HOME/agentville/collector.log" 2>&1 < /dev/null &
   collector_pid=$!
   printf '%s\n' "$collector_pid" > "$XDG_STATE_HOME/agentville/collector.pid"
   ps -p "$collector_pid" -o pid,lstart,args > "$XDG_STATE_HOME/agentville/collector.process"
   ```

   The first command uses the default state directory when the variable is unset. Inspect the log and confirm a fresh report at HQ.

7. To restart after editing the config, read the saved PID and verify that it still belongs to this Collector:

   ```bash
   cat "$XDG_STATE_HOME/agentville/collector.pid"
   cat "$XDG_STATE_HOME/agentville/collector.process"
   ps -p <collector_pid> -o pid,lstart,args
   ```

   Compare the command, start time, and config arguments with the process you started. If the PID has been reused, do not signal it. For the verified Collector, stop it:

   ```bash
   kill -TERM <collector_pid>
   ```

   Wait until that process has exited, then repeat Step 6. Under systemd, use `systemctl --user restart agentville-collector` instead of the nohup procedure.

## Verification

After restart or container recreation, confirm that HQ receives fresh reports and the Colleague detail shows the same colleague ID. A changed colleague ID can indicate missing roster state or a different Project or session; do not infer continuity from a matching display name.

If HQ receives different message content with the same `branch_id` and `seq`, the Collector logs the following warning, at most once per minute:

```text
agentville-collector: possible shared host.id: different messages used the same sequence number; run only one Collector per host.id and give independent copies a new identity
```

An exact retry does not raise it. Lost sequence state can also cause a collision, so this is a diagnostic, not proof of two running Collectors. Stop duplicate Collectors, preserve the intended environment's config and state, and give independent environments separate identities. The warning cannot detect two indistinguishable messages or guarantee detection before sequence numbers collide.
