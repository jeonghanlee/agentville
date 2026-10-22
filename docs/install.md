# Installation Guide

AgentVille runs as the login user, without root, as systemd user services.

| Host role | Installs | Runs |
|---|---|---|
| Branch | `agentville` | `agentville-collector` |
| HQ | `agentville[hq]` | `agentville-hq` and, if agents run there, `agentville-collector` |

## 1. Requirements

- Linux with systemd.
- Python 3.12 or later, `venv`, and `git`.
- On Branches: Claude Code and/or Codex CLI. Codex live state requires its shared app-server daemon.

| Distribution | Packages |
|---|---|
| Debian 13 | `sudo apt install python3 python3-venv git` |
| Rocky Linux 9 | `sudo dnf install python3.12 git` |
| Rocky Linux 10 | `sudo dnf install python3 git` |

Debian 12 ships Python 3.11 and is not supported.

## 2. Download

````bash
git clone https://github.com/jeonghanlee/agentville.git ~/.local/src/agentville
cd ~/.local/src/agentville
````

## 3. Install

Use the Python 3.12 or later interpreter of the host (`python3` on Debian 13 and Rocky Linux 10, `python3.12` on Rocky Linux 9).

````bash
python3 -m venv ~/.local/opt/agentville
~/.local/opt/agentville/bin/pip install '.[hq]'     # Branch only: pip install .
mkdir -p ~/.local/bin
ln -sf ~/.local/opt/agentville/bin/agentville-collector ~/.local/bin/
ln -sf ~/.local/opt/agentville/bin/agentville-hq ~/.local/bin/          # HQ host
````

Check:

````bash
agentville-collector --help
agentville-hq --help                                                    # HQ host
````

## 4. Start the services

````bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/agentville-collector.service ~/.config/systemd/user/
cp deploy/systemd/agentville-hq.service ~/.config/systemd/user/         # HQ host
systemctl --user daemon-reload
systemctl --user enable --now agentville-hq                             # HQ host
systemctl --user enable --now agentville-collector
sudo loginctl enable-linger "$USER"                                     # keep running after logout
````

The first Collector start writes `~/.config/agentville/config.yaml`. Edit it, then `systemctl --user restart agentville-collector`. The settings are described in the [README](../README.md#collector-configuration).

## 5. Verify

````bash
curl -s http://127.0.0.1:8470/health                                    # HQ host: {"status":"ok"}
systemctl --user status agentville-collector
journalctl --user -u agentville-collector -n 50
````

Open `http://127.0.0.1:8470/` on the HQ host. Each Branch appears in the Branches view after its first report.

To print what a Collector would send, without sending it:

````bash
agentville-collector --once --output -
````

## 6. Connect a Branch on another host

On the HQ host:

1. Add the Branch to `~/.config/agentville/tokens.yaml` (mode 0600). The key is the Branch's `host.id` from its `config.yaml`; the value is a random string of at least 16 characters, for example from `openssl rand -hex 24`.
2. Create `~/.config/agentville/viewer.token` (mode 0600) with another random string.
3. Expose HQ over HTTPS and restart it with the token options. Either:
   - behind a reverse proxy on the HQ host: `agentville-hq --host 127.0.0.1 --no-trust-loopback --tokens ~/.config/agentville/tokens.yaml --viewer-token-file ~/.config/agentville/viewer.token --server-name hq.example.org`
   - or directly: `agentville-hq --host 0.0.0.0 --allow-remote --tokens ~/.config/agentville/tokens.yaml --viewer-token-file ~/.config/agentville/viewer.token`

   Put the chosen options into `ExecStart` of `~/.config/systemd/user/agentville-hq.service`, then `systemctl --user daemon-reload && systemctl --user restart agentville-hq`.

On the Branch:

1. In `~/.config/agentville/config.yaml` set `hq.url: https://hq.example.org` and `hq.token` to the Branch's token. The file must stay mode 0600.
2. `systemctl --user restart agentville-collector`.

Open `https://hq.example.org/#token=<viewer token>` in the browser.

## 7. Upgrade

````bash
cd ~/.local/src/agentville
git pull
~/.local/opt/agentville/bin/pip install '.[hq]'                         # Branch only: pip install .
systemctl --user restart agentville-collector
systemctl --user restart agentville-hq                                  # HQ host
````

Configuration, roster, and HQ data are kept.

## 8. Uninstall

````bash
systemctl --user disable --now agentville-collector agentville-hq
rm -f ~/.config/systemd/user/agentville-collector.service ~/.config/systemd/user/agentville-hq.service
rm -f ~/.local/bin/agentville-collector ~/.local/bin/agentville-hq
rm -rf ~/.local/opt/agentville ~/.local/src/agentville
````

Data left in place, to be removed separately if no longer needed:

| Path | Content |
|---|---|
| `~/.config/agentville/` | Collector configuration, HQ token files |
| `~/.local/state/agentville/` | Collector `seq` and `roster.json` |
| `~/.local/share/agentville/hq.sqlite3` | HQ database |
