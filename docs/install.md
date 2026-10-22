# Installation Guide

AgentVille runs as the login user, without root, as systemd user services.

| Host role | Installs | Runs |
|---|---|---|
| Branch | `agentville` | `agentville-collector` |
| HQ | `agentville[hq]` | `agentville-hq` and, if agents run there, `agentville-collector` |

## 1. Requirements

- Linux with a systemd user instance. Without systemd, start the two programs in the foreground or with any process supervisor, using the same arguments as the `ExecStart` lines of the unit files in `deploy/systemd/`.
- Python 3.12 or later, `venv`, and `git`.
- On Branches: Claude Code and/or Codex CLI. Codex live state requires its shared app-server daemon.

| Distribution | Packages |
|---|---|
| Debian 13 | `sudo apt install python3 python3-venv git` |
| Ubuntu 24.04 | `sudo apt install python3 python3-venv git` |
| Rocky Linux 9 | `sudo dnf install python3.12 git` |
| Rocky Linux 10 | `sudo dnf install python3 git` |

Debian 12 ships Python 3.11 and is not supported.

## 2. Download

````bash
git clone -b claude/modest-albattani-dn2ho3 https://github.com/jeonghanlee/agentville.git ~/.local/src/agentville
cd ~/.local/src/agentville
````

## 3. Install

Use the Python 3.12 or later interpreter of the host: `python3` on Debian 13, Ubuntu 24.04, and Rocky Linux 10; `python3.12` on Rocky Linux 9.

Branch only:

````bash
python3 -m venv ~/.local/opt/agentville
~/.local/opt/agentville/bin/pip install .
mkdir -p ~/.local/bin
ln -sf ~/.local/opt/agentville/bin/agentville-collector ~/.local/bin/
````

HQ host:

````bash
python3 -m venv ~/.local/opt/agentville
~/.local/opt/agentville/bin/pip install '.[hq]'
mkdir -p ~/.local/bin
ln -sf ~/.local/opt/agentville/bin/agentville-collector ~/.local/bin/
ln -sf ~/.local/opt/agentville/bin/agentville-hq ~/.local/bin/
````

The commands in this guide call the programs by name, so `~/.local/bin` must be on `PATH`. If `command -v agentville-collector` prints nothing, add `export PATH="$HOME/.local/bin:$PATH"` to `~/.bashrc` and open a new shell. The unit files use the full path and do not depend on `PATH`.

Check:

````bash
agentville-collector --help
agentville-hq --help                                                    # HQ host
````

## 4. Start the services

Create and edit the Collector configuration before the first service start, so the Collector reports to the intended HQ from the beginning. This run writes `~/.config/agentville/config.yaml` (mode 0600) and nothing else:

````bash
agentville-collector --once --output /dev/null
````

Set `hq.url` and the other values in that file (see the [README](../README.md#collector-configuration)), then enable the services.

Branch only:

````bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/agentville-collector.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now agentville-collector
````

HQ host:

````bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/agentville-hq.service deploy/systemd/agentville-collector.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now agentville-hq agentville-collector
````

HQ listens on `127.0.0.1:8470`. When that port is taken (`ss -ltn 'sport = :8470'` lists a listener), choose another port, for example 8471, before enabling the services:

- in `~/.config/systemd/user/agentville-hq.service`, change `--port 8470` in `ExecStart` to `--port 8471`;
- in `~/.config/agentville/config.yaml` of every Collector reporting to this HQ, set `hq.url: http://127.0.0.1:8471` (the file is written at the first Collector start; set it, then restart the Collector);
- use the same port in the addresses of Section 5.

User services run while the user is logged in. To keep them running after logout and start them at boot, an administrator can enable lingering for the user; this is optional and is the only step that needs root:

````bash
sudo loginctl enable-linger <user>
````

Without systemd, the same programs in the foreground:

````bash
agentville-hq --host 127.0.0.1 --port 8470                              # HQ host
agentville-collector
````

After a later edit of `config.yaml`, run `systemctl --user restart agentville-collector`.

On the HQ host the Collector may start before HQ listens; its first delivery then fails with `delivery failed: … Connection refused` and the next retry succeeds.

## 5. Verify

Each program writes one line to standard error at start:

````text
agentville-hq: serving http://127.0.0.1:8470/ (database /home/<user>/.local/share/agentville/hq.sqlite3)
agentville-collector: Branch <alias> (<host.id>) reporting to http://127.0.0.1:8470
````

Messages and errors go to standard error: in the terminal when run in the foreground, and to the user journal under systemd:

````bash
journalctl --user -u agentville-collector -n 50
journalctl --user -u agentville-hq -n 50                                # HQ host
````

A Collector that cannot reach HQ logs `agentville-collector: delivery failed: <reason>` on each attempt, for example `delivery failed: HTTP 401 token required`. An unusable configuration or option stops the program with a message containing `agentville-collector:` or `agentville-hq:`.

On the HQ host:

````bash
curl -s http://127.0.0.1:8470/health                                    # {"status":"ok"}
````

Open `http://127.0.0.1:8470/` on the HQ host. Each Branch appears in the Branches view after its first report.

To print what a Collector would send, without sending it and without writing its state files:

````bash
agentville-collector --once --output -
````

## 6. Connect a Branch on another host

A Branch on another host needs three things from HQ: a token listed for its `host.id`, an HTTPS address, and, for browsers, a viewer token. Examples use `hq.example.org` as the public name of the HQ host.

### 6.1 Read the Branch host.id

On the Branch, after its first Collector start:

````bash
grep -m1 '^  id:' ~/.config/agentville/config.yaml
````

The value after `id:` is the `host.id`. The startup line of the Collector shows it as well.

### 6.2 Create the token files

On the HQ host. Each line of `tokens.yaml` is `<host.id>: <token>`, one line per Branch; a token is a string of at least 16 characters. Both files must be mode 0600.

````bash
mkdir -p ~/.config/agentville
install -m600 /dev/null ~/.config/agentville/viewer.token
python3 -c 'import secrets; print(secrets.token_hex(24))' > ~/.config/agentville/viewer.token
touch ~/.config/agentville/tokens.yaml && chmod 600 ~/.config/agentville/tokens.yaml
echo "<branch host.id>: $(python3 -c 'import secrets; print(secrets.token_hex(24))')" >> ~/.config/agentville/tokens.yaml
````

Repeat the last line for each Branch. `cat ~/.config/agentville/tokens.yaml` shows the token to set on that Branch.

### 6.3 Serve HQ over HTTPS

Choose one of the two forms. In both, edit `ExecStart` in `~/.config/systemd/user/agentville-hq.service` and apply it:

````bash
systemctl --user daemon-reload
systemctl --user restart agentville-hq
````

Unit files expand `%h` to the home directory; they do not expand `~`.

**(a) HQ serves HTTPS directly.** HQ needs a PEM certificate and key for `hq.example.org`, readable by the login user (key mode 0600). The Collector verifies the certificate against the host's system trust store, so each Branch must trust its issuer. The paths below are examples.

````ini
ExecStart=%h/.local/bin/agentville-hq --host 0.0.0.0 --port 8470 --allow-remote \
    --tls-cert %h/.config/agentville/tls/cert.pem --tls-key %h/.config/agentville/tls/key.pem \
    --tokens %h/.config/agentville/tokens.yaml \
    --viewer-token-file %h/.config/agentville/viewer.token
````

- HQ address: `https://hq.example.org:8470`. The startup line reads `agentville-hq: serving https://0.0.0.0:8470/ (database …)`.
- On a non-loopback bind every Branch needs a token, including the Collector on the HQ host. Add the HQ host's `host.id` to `tokens.yaml` and configure that Collector like any other Branch (Section 6.5), with `hq.url: https://hq.example.org:8470`. HQ speaks only HTTPS on its port in this form.

**(b) Reverse proxy on the HQ host.** HQ stays on `127.0.0.1:8470` and the proxy terminates TLS.

````ini
ExecStart=%h/.local/bin/agentville-hq --host 127.0.0.1 --port 8470 \
    --no-trust-loopback --server-name hq.example.org \
    --tokens %h/.config/agentville/tokens.yaml \
    --viewer-token-file %h/.config/agentville/viewer.token
````

A minimal nginx server block (installed by an administrator). It passes the `Host` header and upgrades the live WebSocket at `/ws/v1/live`:

````nginx
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
````

- HQ address: `https://hq.example.org`.
- With `--no-trust-loopback`, requests through the proxy arrive from loopback and every Branch needs a token, including the Collector on the HQ host. Add the HQ host's `host.id` to `tokens.yaml` and set `hq.token` in its `config.yaml`, keeping `hq.url: http://127.0.0.1:8470`.

### 6.4 Firewall

On the HQ host, open only the HTTPS port: 8470/tcp in form (a), 443/tcp in form (b). For example, for form (b):

````bash
sudo firewall-cmd --permanent --add-port=443/tcp && sudo firewall-cmd --reload   # firewalld (Rocky Linux)
sudo ufw allow 443/tcp                                                         # ufw
````

### 6.5 Configure the Branch

In `~/.config/agentville/config.yaml` on the Branch (the file stays mode 0600):

````yaml
hq:
  url: https://hq.example.org          # form (a): https://hq.example.org:8470
  token: <token listed for this host.id>
````

Then `systemctl --user restart agentville-collector`. The startup line reads `agentville-collector: Branch <alias> (<host.id>) reporting to https://hq.example.org`.

- The Collector does not follow redirects; `hq.url` is the final HTTPS address.
- A token over plain HTTP to a non-loopback HQ is refused: the Collector exits with `agentville-collector: hq.url http://…: refusing to send a token over plain HTTP to a non-loopback HQ; use https`.
- HQ answers a missing token with `HTTP 401 token required` and a token that does not match with `HTTP 401 invalid token`; the Collector logs either as `delivery failed: …`.

### 6.6 Open the office

The viewer token is in `~/.config/agentville/viewer.token` on the HQ host. Open `https://hq.example.org/#token=<viewer token>` (form (a): `https://hq.example.org:8470/#token=<viewer token>`). The page moves the token to session storage and removes it from the address bar.

In form (b), a browser on the HQ host can also open `http://127.0.0.1:8470/#token=<viewer token>`.

### 6.7 Rotate tokens

HQ reads `tokens.yaml` and `viewer.token` only at start.

- Branch token: replace its line in `tokens.yaml` and `systemctl --user restart agentville-hq`; on the Branch, set the new `hq.token` and `systemctl --user restart agentville-collector`. Deleting the line and restarting HQ revokes the Branch.
- Viewer token: write a new value to `viewer.token`, restart HQ, and open the page with the new `#token=`.

## 7. Upgrade

Branch only:

````bash
cd ~/.local/src/agentville
git pull
~/.local/opt/agentville/bin/pip install .
systemctl --user restart agentville-collector
````

HQ host:

````bash
cd ~/.local/src/agentville
git pull
~/.local/opt/agentville/bin/pip install '.[hq]'
systemctl --user restart agentville-hq agentville-collector
````

Configuration, roster, HQ data, and the installed unit files are kept.

## 8. Uninstall

Branch only:

````bash
systemctl --user disable --now agentville-collector
rm -f ~/.config/systemd/user/agentville-collector.service
systemctl --user daemon-reload
rm -f ~/.local/bin/agentville-collector
rm -rf ~/.local/opt/agentville ~/.local/src/agentville
````

HQ host:

````bash
systemctl --user disable --now agentville-collector agentville-hq
rm -f ~/.config/systemd/user/agentville-collector.service ~/.config/systemd/user/agentville-hq.service
systemctl --user daemon-reload
rm -f ~/.local/bin/agentville-collector ~/.local/bin/agentville-hq
rm -rf ~/.local/opt/agentville ~/.local/src/agentville
````

Data left in place, to be removed separately if no longer needed:

| Path | Content |
|---|---|
| `~/.config/agentville/` | Collector configuration; on HQ, token files |
| `~/.local/state/agentville/` | Collector `seq` and `roster.json` |
| `~/.local/share/agentville/hq.sqlite3` | HQ database (HQ host) |
