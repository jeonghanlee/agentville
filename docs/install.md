# Installation Guide

## Scope

This document covers installing AgentVille from the repository as the login user, running it as systemd user services, connecting Branches on other hosts, upgrading, and removing it.

**Out of scope:** Collector settings ([Configuration](configuration.md)) and the office page ([Using the Office](using.md)).

AgentVille runs as the login user, without root, as systemd user services.

| Host role | Installs | Runs |
|---|---|---|
| Branch | `agentville` | `agentville-collector` |
| HQ | `agentville[hq]` | `agentville-hq` and, if agents run there, `agentville-collector` |

## 1. Requirements

- Linux with a systemd user instance. Without systemd, start the two programs in the foreground or with any process supervisor, using the same arguments as the `ExecStart` lines of the unit files in `deploy/systemd/`.
- Python 3.12 or later, `venv`, and `git`.
- On Branches: Claude Code and/or Codex CLI. Codex runs that use its shared app-server daemon are observed live, including `waiting`. Other Codex runs (e.g. `codex exec`) are observed from their rollout files only, with low confidence and without `waiting` ([Architecture](architecture.md) Section 3.4).

| Distribution | Packages |
|---|---|
| Debian 13 | `sudo apt install python3 python3-venv git` |
| Ubuntu 24.04 | `sudo apt install python3 python3-venv git` |
| Rocky Linux 9 | `sudo dnf install python3.12 git` |
| Rocky Linux 10 | `sudo dnf install python3 git` |

Debian 12 ships Python 3.11 and is not supported.

## 2. Download

`install.sh` performs Sections 2 to 4 with the paths below and installs the latest release:

```bash
curl -fsSL https://raw.githubusercontent.com/jeonghanlee/agentville/master/install.sh | bash                 # Branch only
curl -fsSL https://raw.githubusercontent.com/jeonghanlee/agentville/master/install.sh | bash -s -- --hq      # HQ host
```

| Option | Effect |
|---|---|
| `--hq` | Also installs HQ and its service. |
| `--ref <ref>` | Installs a release tag, branch, or commit instead of the latest release tag. |
| `--hq-url <url>` | Sets `hq.url` in the Collector configuration (Section 6.5). |
| `--token-file <file>` | Sets `hq.token` from the file (Section 6.5). |
| `--no-start` | Installs the unit files without enabling or restarting the services. |

It writes the Collector configuration before the first service start, copies a unit file only when none is installed, and then enables and restarts the services and checks that they are running. Without a systemd user instance it prints the foreground commands instead. It stops without changes when `~/.local/src/agentville` has local changes. Continue with Section 5.

A Branch reporting to an HQ on another host needs a token for its `host.id` (Section 6.1), which the first run writes. Run the script once, create the token on HQ (Section 6.2), then run it again with `--hq-url` set to the HQ HTTPS address (Sections 6.3 and 6.5) and `--token-file` naming a file that holds only this Branch's token value, not the `<host.id>: <token>` line.

The manual steps:

```bash
git clone https://github.com/jeonghanlee/agentville.git ~/.local/src/agentville
cd ~/.local/src/agentville
```

## 3. Install

Use the Python 3.12 or later interpreter of the host: `python3` on Debian 13, Ubuntu 24.04, and Rocky Linux 10; `python3.12` on Rocky Linux 9.

Branch only:

```bash
python3 -m venv ~/.local/opt/agentville
~/.local/opt/agentville/bin/pip install .
mkdir -p ~/.local/bin
ln -sf ~/.local/opt/agentville/bin/agentville-collector ~/.local/bin/
```

HQ host:

```bash
python3 -m venv ~/.local/opt/agentville
~/.local/opt/agentville/bin/pip install '.[hq]'
mkdir -p ~/.local/bin
ln -sf ~/.local/opt/agentville/bin/agentville-collector ~/.local/bin/
ln -sf ~/.local/opt/agentville/bin/agentville-hq ~/.local/bin/
```

The commands in this guide call the programs by name, so `~/.local/bin` must be on `PATH`. If `command -v agentville-collector` prints nothing, add `export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc` and open a new shell. The unit files use the full path and do not depend on `PATH`.

Check:

```bash
agentville-collector --version                                          # agentville-collector 0.2.0
agentville-hq --version                                                 # HQ host: agentville-hq 0.2.0
```

## 4. Start the services

Create and edit the Collector configuration before the first service start, so the Collector reports to the intended HQ from the beginning. This run writes `~/.config/agentville/config.yaml` (mode 0600) and nothing else:

```bash
agentville-collector --once --output /dev/null
```

Set `hq.url` and the other values in that file (see [Configuration](configuration.md)), then enable the services.

Branch only:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/agentville-collector.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now agentville-collector
```

HQ host:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/agentville-hq.service deploy/systemd/agentville-collector.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now agentville-hq agentville-collector
```

HQ listens on `127.0.0.1:8470`. When that port is taken (`ss -ltn 'sport = :8470'` lists a listener, and HQ stops with `agentville-hq: cannot listen on 127.0.0.1:8470: Address already in use`), choose another port, for example 8471. If the listener is an HQ you started yourself (for example from the README quick start), stop it instead of changing the port.

To change the port:

- in `~/.config/systemd/user/agentville-hq.service`, change `--port 8470` in `ExecStart` to `--port 8471`, then run `systemctl --user daemon-reload` and `systemctl --user restart agentville-hq`;
- in `~/.config/agentville/config.yaml` of every Collector reporting to this HQ, set `hq.url: http://127.0.0.1:8471` (the file is written at the first Collector start; set it, then restart the Collector);
- use the same port in the addresses of Section 5.

HQ keeps its database in `$XDG_DATA_HOME/agentville/hq.sqlite3` (default `~/.local/share/agentville/hq.sqlite3`; the directory is created with mode 0700). To place it elsewhere, add `--db <path>` to `ExecStart`. Received messages and the state history (used by the work log and timeline replay) are kept for 30 days; `--retention-days <n>` changes that. The current state of each Branch is kept regardless. An HQ database from 0.1.0 starts its history at the first start after the upgrade.

User services run while the user is logged in. To keep them running after logout and start them at boot, an administrator can enable lingering for the user (optional; the services themselves never need root):

```bash
sudo loginctl enable-linger <user>
```

Without systemd, the same programs in the foreground:

```bash
agentville-hq --host 127.0.0.1 --port 8470                              # HQ host
agentville-collector
```

After a later edit of `config.yaml`, run `systemctl --user restart agentville-collector`.

On the HQ host the Collector may start before HQ listens; its first delivery then fails with `delivery failed: ... Connection refused` and the next retry succeeds.

## 5. Verify

Each program writes one line to standard error at start; HQ writes it once its port is bound and its TLS certificate, if any, is loaded:

```text
agentville-hq: serving http://127.0.0.1:8470/ (database /home/<user>/.local/share/agentville/hq.sqlite3)
agentville-collector: Branch <alias> (<host.id>) reporting to http://127.0.0.1:8470
```

Messages and errors go to standard error: in the terminal when run in the foreground, and to the user journal under systemd:

```bash
journalctl --user -u agentville-collector -n 50
journalctl --user -u agentville-hq -n 50                                # HQ host
```

A Collector that cannot reach HQ logs `agentville-collector: delivery failed: <reason>` on each attempt, for example `delivery failed: HTTP 401 token required`. An unusable configuration or option stops the program with one line starting with `agentville-collector:` or `agentville-hq:` that names the file or option and the reason, for example `agentville-collector: invalid configuration: collector.poll_interval must be greater than 0` or `agentville-hq: /home/<user>/.config/agentville/tokens.yaml: No such file or directory`.

On the HQ host:

```bash
curl -s http://127.0.0.1:8470/health                                    # {"status":"ok"}
```

Open `http://127.0.0.1:8470/` on the HQ host. Each Branch appears in the Branches view after its first report.

To print what a Collector would send, without sending it and without writing its state files:

```bash
agentville-collector --once --output -
```

## 6. Connect a Branch on another host

A Branch on another host needs three things from HQ: a token listed for its `host.id`, an HTTPS address, and, for browsers, a viewer token. Examples use `hq.example.org` as the public name of the HQ host.

### 6.1 Read the Branch host.id

On the Branch, after its first Collector start:

```bash
grep -m1 '^  id:' ~/.config/agentville/config.yaml
```

The value after `id:` is the `host.id`. The startup line of the Collector shows it as well.

### 6.2 Create the token files

On the HQ host. Each line of `tokens.yaml` is `<host.id>: <token>`, one line per Branch; a token is a string of at least 16 characters. Both files must be mode 0600.

```bash
mkdir -p ~/.config/agentville
install -m600 /dev/null ~/.config/agentville/viewer.token
python3 -c 'import secrets; print(secrets.token_hex(24))' > ~/.config/agentville/viewer.token
touch ~/.config/agentville/tokens.yaml && chmod 600 ~/.config/agentville/tokens.yaml
echo "<branch host.id>: $(python3 -c 'import secrets; print(secrets.token_hex(24))')" >> ~/.config/agentville/tokens.yaml
```

Repeat the last line for each Branch. `cat ~/.config/agentville/tokens.yaml` shows the token to set on that Branch.

### 6.3 Serve HQ over HTTPS

Choose one of the two forms. In both, edit `ExecStart` in `~/.config/systemd/user/agentville-hq.service` and apply it:

```bash
systemctl --user daemon-reload
systemctl --user restart agentville-hq
```

Unit files expand `%h` to the home directory; they do not expand `~`. Without systemd, run the command after `ExecStart=` in the foreground, in its own terminal, with `~` in place of `%h`; where this guide says `systemctl --user restart ...`, stop the program (Ctrl-C) and start it again.

**(a) HQ serves HTTPS directly.** HQ needs a PEM certificate and key for `hq.example.org`, readable by the login user (key mode 0600). The Collector verifies the certificate against the host's system trust store, so each Branch, and the HQ host for its own Collector, must trust its issuer. Until it does, the Collector logs `delivery failed: ... CERTIFICATE_VERIFY_FAILED`. To trust a self-signed certificate, copy HQ's `cert.pem` (named in the example below) to each host first; for an internal CA, use the CA certificate instead of `cert.pem`. Then:

| System | Command |
|---|---|
| Debian, Ubuntu | `sudo cp cert.pem /usr/local/share/ca-certificates/agentville-hq.crt && sudo update-ca-certificates` |
| Rocky Linux | `sudo cp cert.pem /etc/pki/ca-trust/source/anchors/agentville-hq.pem && sudo update-ca-trust` |

The paths below are examples.

```ini
ExecStart=%h/.local/bin/agentville-hq --host 0.0.0.0 --port 8470 --allow-remote \
    --tls-cert %h/.config/agentville/tls/cert.pem --tls-key %h/.config/agentville/tls/key.pem \
    --tokens %h/.config/agentville/tokens.yaml \
    --viewer-token-file %h/.config/agentville/viewer.token
```

- HQ address: `https://hq.example.org:8470`. The startup line reads `agentville-hq: serving https://0.0.0.0:8470/ (database ...)`.
- On a non-loopback bind every Branch needs a token, including the Collector on the HQ host. Add the HQ host's `host.id` to `tokens.yaml` and configure that Collector like any other Branch (Section 6.5), with `hq.url: https://hq.example.org:8470`. HQ speaks only HTTPS on its port in this form.

**(b) Reverse proxy on the HQ host.** HQ stays on `127.0.0.1:8470` and the proxy terminates TLS.

```ini
ExecStart=%h/.local/bin/agentville-hq --host 127.0.0.1 --port 8470 \
    --no-trust-loopback --server-name hq.example.org \
    --tokens %h/.config/agentville/tokens.yaml \
    --viewer-token-file %h/.config/agentville/viewer.token
```

A minimal nginx server block (installed by an administrator). It passes the `Host` header and upgrades the live WebSocket at `/ws/v1/live`:

```nginx
server {
    listen 443 ssl;
    server_name hq.example.org;
    ssl_certificate     /etc/ssl/certs/hq.example.org.pem;
    ssl_certificate_key /etc/ssl/private/hq.example.org.key;

    location / {
        proxy_pass http://127.0.0.1:8470;
        proxy_set_header Host $host;
    }

    location /ws/v1/live {
        proxy_pass http://127.0.0.1:8470;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

- HQ address: `https://hq.example.org`.
- With `--no-trust-loopback`, requests through the proxy arrive from loopback and every Branch needs a token, including the Collector on the HQ host. Add the HQ host's `host.id` to `tokens.yaml` and set `hq.token` in its `config.yaml`, keeping `hq.url: http://127.0.0.1:8470`.

### 6.4 Firewall

On the HQ host, open only the HTTPS port: 8470/tcp in form (a), 443/tcp in form (b). For example, for form (b):

```bash
sudo firewall-cmd --permanent --add-port=443/tcp && sudo firewall-cmd --reload   # firewalld (Rocky Linux)
sudo ufw allow 443/tcp                                                         # ufw
```

### 6.5 Configure the Branch

In `~/.config/agentville/config.yaml` on the Branch (the file stays mode 0600):

```yaml
hq:
  url: https://hq.example.org          # form (a): https://hq.example.org:8470
  token: <token listed for this host.id>
```

Then `systemctl --user restart agentville-collector`. The startup line reads `agentville-collector: Branch <alias> (<host.id>) reporting to https://hq.example.org`.

- The Collector does not follow redirects; `hq.url` is the final HTTPS address.
- A token over plain HTTP to a non-loopback HQ is refused: the Collector exits with `agentville-collector: hq.url http://...: refusing to send a token over plain HTTP to a non-loopback HQ; use https`.
- HQ answers a missing token with `HTTP 401 token required` and a token that does not match with `HTTP 401 invalid token`; the Collector logs either as `delivery failed: ...`.

### 6.6 Open the office

The viewer token is in `~/.config/agentville/viewer.token` on the HQ host. Open `https://hq.example.org/#token=<viewer token>` (form (a): `https://hq.example.org:8470/#token=<viewer token>`) in a new tab; if the page is already open, add the fragment and reload. The page moves the token to session storage and removes it from the address bar. A wrong or old token shows the same "Viewer token required" as a missing one; reopen with the current value of `viewer.token`.

In form (b), a browser on the HQ host can also open `http://127.0.0.1:8470/#token=<viewer token>`.

### 6.7 Rotate tokens

HQ reads `tokens.yaml` and `viewer.token` only at start.

- Branch token: replace its line in `tokens.yaml` and `systemctl --user restart agentville-hq`; on the Branch, set the new `hq.token` and `systemctl --user restart agentville-collector`. Deleting the line and restarting HQ revokes the Branch.
- Viewer token: write a new value to `viewer.token`, restart HQ, and open the page with the new `#token=`.

## 7. External notifications

HQ can post notifications to an [ntfy](https://ntfy.sh) topic, so a phone or desktop subscribed to the topic is notified without an open browser tab. They are off by default.

The rules are those of browser notifications ([Using the Office](using.md), Settings): a colleague starts waiting or has an error, and a Branch stops or resumes reporting. Nothing is sent when HQ starts, for a colleague or Branch seen for the first time, or for changes that arrive with a Branch snapshot, for example after a Collector restart. Each colleague and Branch is notified at most once per 30 s; a change within that time is sent at its end if it still holds. More than three at once become one summary. [Data and Security](data.md) lists what is sent.

Create the file with mode 0600:

```bash
install -m600 /dev/null ~/.config/agentville/notify.yaml
```

```yaml
url: https://ntfy.sh/<topic>                     # https unless the host is loopback
token_file: ~/.config/agentville/ntfy.token       # optional; mode 0600
events: [waiting, error, branch]                 # optional; default all three
language: en                                     # optional; en or ko
```

| Key | Value |
|---|---|
| `url` | The topic URL. Subscribe to the same topic in the ntfy app. |
| `token_file` | A file holding an ntfy access token, for a server with access control. Mode 0600: `install -m600 /dev/null ~/.config/agentville/ntfy.token`, then write the token into it. |
| `events` | `waiting`: a colleague starts waiting. `error`: a colleague has an error. `branch`: a Branch stops or resumes reporting. |
| `language` | Language of the texts: `en` or `ko`. |

On a public server such as ntfy.sh, anyone who knows a topic name can read it. Use a long random name, for example from `python3 -c 'import secrets; print("agentville-" + secrets.token_hex(12))'`, or a server with access control and a token.

Append the option to the existing `ExecStart` line in `~/.config/systemd/user/agentville-hq.service`, keeping every option already there (for example those of Section 6.3), then reload and restart. With the default line:

```ini
ExecStart=%h/.local/bin/agentville-hq --host 127.0.0.1 --port 8470 \
    --notify-config %h/.config/agentville/notify.yaml
```

```bash
systemctl --user daemon-reload
systemctl --user restart agentville-hq
```

- HQ reads the file at start only; restart HQ after editing it.
- An invalid file stops HQ with one line, for example `agentville-hq: /home/<user>/.config/agentville/notify.yaml: url must use https unless its host is loopback`.
- Sending runs in the background and never delays Branch reports. A failure is logged at most once a minute, for example `agentville-hq: notification failed: URLError: <urlopen error [Errno 111] Connection refused>` in `journalctl --user -u agentville-hq`.

## 8. Upgrade

Branch only:

```bash
cd ~/.local/src/agentville
git pull
rm -rf build
~/.local/opt/agentville/bin/pip install .
systemctl --user restart agentville-collector
```

HQ host:

```bash
cd ~/.local/src/agentville
git pull
rm -rf build
~/.local/opt/agentville/bin/pip install '.[hq]'
systemctl --user restart agentville-hq agentville-collector
```

Installed with `install.sh`: run the same command again; it moves to the latest release (or `--ref`) and, unless `--no-start` is given or systemd is absent, restarts the services. It leaves the source on a detached commit, so the `git pull` steps above apply only to a manual installation.

Configuration, roster, HQ data, and the installed unit files are kept.

## 9. Uninstall

Branch only:

```bash
systemctl --user disable --now agentville-collector
rm -f ~/.config/systemd/user/agentville-collector.service
systemctl --user daemon-reload
rm -f ~/.local/bin/agentville-collector
rm -rf ~/.local/opt/agentville ~/.local/src/agentville
```

HQ host:

```bash
systemctl --user disable --now agentville-collector agentville-hq
rm -f ~/.config/systemd/user/agentville-collector.service ~/.config/systemd/user/agentville-hq.service
systemctl --user daemon-reload
rm -f ~/.local/bin/agentville-collector ~/.local/bin/agentville-hq
rm -rf ~/.local/opt/agentville ~/.local/src/agentville
```

Data left in place, to be removed separately if no longer needed:

| Path | Content |
|---|---|
| `~/.config/agentville/` | Collector configuration; on HQ, token files, the notification configuration, and, in form (a) with the example paths, the TLS certificate and private key |
| `~/.local/state/agentville/` | Collector `seq` and `roster.json` |
| `~/.local/share/agentville/hq.sqlite3` | HQ database (HQ host) |
