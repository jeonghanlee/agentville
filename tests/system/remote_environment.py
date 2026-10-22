"""Exercise real SSH, Docker, installed Collectors, and HQ with retained evidence.

Run with the repository's Python environment: python tests/system/remote_environment.py.
Only containers created by this invocation are stopped. Images, volumes, receipts,
and generated SSH keys remain in a fresh private temporary directory or Docker.
"""

import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

import uvicorn
import yaml

from agentville.hq.app import create_app
from agentville.hq.store import Store

ROOT = Path(__file__).resolve().parents[2]


def main():
    workspace = Path(tempfile.mkdtemp(prefix="agentville-030-system-"))
    os.chmod(workspace, 0o700)
    receipts = (workspace / "commands.jsonl").open("a")
    prefix = "agentville030-" + uuid.uuid4().hex[:10]
    containers, tunnels = [], []
    checks = []

    def run(args, check=True):
        result = subprocess.run(args, capture_output=True, text=True, timeout=300)
        receipts.write(json.dumps({"args": args, "status": result.returncode,
                                   "stdout": result.stdout, "stderr": result.stderr}) + "\n")
        receipts.flush()
        if check and result.returncode:
            raise RuntimeError(f"command failed ({result.returncode}): {args[:3]}; see {workspace}")
        return result

    def free_port():
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    def exec_in(container, args, user="1000:1000"):
        return run(["docker", "exec", "--user", user, container, *args])

    def verify(name, condition):
        checks.append({"check": name, "passed": bool(condition)})
        (workspace / "results.json").write_text(json.dumps(checks, indent=2))
        if not condition:
            raise AssertionError(name)
        print(f"PASS: {name}", flush=True)

    server = None
    server_thread = None
    print(f"Evidence: {workspace}", flush=True)
    try:
        key = workspace / "client_key"
        run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)])
        context = workspace / "context"
        context.mkdir()
        shutil.copytree(ROOT / "packages", context / "packages", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(ROOT / "pyproject.toml", context)
        shutil.copy(ROOT / "tests/system/Dockerfile", context)
        shutil.copy(ROOT / "tests/system/agent.py", context)
        shutil.copy(str(key) + ".pub", context / "authorized_keys")
        image = prefix + ":test"
        run(["docker", "build", "--progress=plain", "-t", image, str(context)])
        volumes = [prefix + "-config", prefix + "-state"]
        for volume in volumes:
            run(["docker", "volume", "create", volume])
        mounts = ["-v", volumes[0] + ":/config", "-v", volumes[1] + ":/state"]
        env = ["-e", "XDG_CONFIG_HOME=/config", "-e", "XDG_STATE_HOME=/state"]
        forward_port, ssh_port = free_port(), free_port()
        gateway = run(["docker", "network", "inspect", "bridge", "--format", "{{(index .IPAM.Config 0).Gateway}}"]).stdout.strip()
        hq_port = free_port()
        token = uuid.uuid4().hex
        saved = None
        for number in (1, 2):
            container = prefix + f"-host-{number}"
            run(["docker", "run", "-d", "--name", container, "--network", "host", *mounts, *env, image,
                 "/usr/sbin/sshd", "-D", "-e", "-p", str(ssh_port), "-o", "ListenAddress=" + gateway,
                 "-o", "PasswordAuthentication=no", "-o", "AllowUsers=dev"])
            containers.append(container)
            exec_in(container, ["git", "init", "-q", "/workspace/agentville"])
            exec_in(container, ["git", "remote", "add", "origin", "https://github.com/example/agentville-test.git"])
            if number == 1:
                verify("fresh volumes belong to root", exec_in(container, ["stat", "-c", "%u", "/config"], user="0").stdout.strip() == "0")
            exec_in(container, ["chown", "-R", "1000:1000", "/config", "/state"], user="0")
            exec_in(container, ["agentville-collector", "--once", "--output", "/dev/null"])
            config = yaml.safe_load(exec_in(container, ["cat", "/config/agentville/config.yaml"]).stdout)
            config["hq"] = {"url": f"http://127.0.0.1:{forward_port}", "token": token}
            config["providers"] = {"claude": [{"home": "/home/dev/.claude"}]}
            config_path = workspace / "collector.yaml"
            config_path.write_text(yaml.safe_dump(config))
            os.chmod(config_path, 0o600)
            run(["docker", "cp", str(config_path), container + ":/config/agentville/config.yaml"])
            exec_in(container, ["chown", "1000:1000", "/config/agentville/config.yaml"], user="0")
            if server is None:
                store = Store(str(workspace / "hq.sqlite3"))
                app = create_app(store, tokens={config["host"]["id"]: token},
                                 trust_loopback=False)
                server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=hq_port, log_level="error"))
                server_thread = threading.Thread(target=server.run, daemon=True)
                server_thread.start()
                deadline = time.monotonic() + 10
                while not server.started and time.monotonic() < deadline:
                    time.sleep(0.05)
                verify("HQ readiness", server.started)
            ssh_base = ["ssh", "-F", "/dev/null", "-i", str(key), "-p", str(ssh_port), "-o", "BatchMode=yes",
                        "-o", "ConnectTimeout=2", "-o", "StrictHostKeyChecking=no",
                        "-o", "UserKnownHostsFile=" + str(workspace / "known_hosts")]
            deadline = time.monotonic() + 20
            while True:
                ready = run([*ssh_base, "dev@" + gateway, "true"], check=False)
                if ready.returncode == 0:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError("isolated SSH server did not become ready")
                time.sleep(0.2)
            tunnel = subprocess.Popen([*ssh_base, "-N", "-o", "ExitOnForwardFailure=yes", "-R",
                                       f"127.0.0.1:{forward_port}:127.0.0.1:{hq_port}", "dev@" + gateway],
                                      stdout=subprocess.DEVNULL, stderr=(workspace / f"ssh-{number}.log").open("w"))
            tunnels.append(tunnel)
            deadline = time.monotonic() + 10
            while True:
                if tunnel.poll() is not None:
                    raise RuntimeError(f"SSH reverse tunnel exited ({tunnel.returncode}); see {workspace}")
                try:
                    with socket.create_connection(("127.0.0.1", forward_port), timeout=0.2):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.05)
            run(["docker", "exec", "-d", "--user", "1000:1000", container, "python", "/verification/agent.py"])
            deadline = time.monotonic() + 10
            while run(["docker", "exec", "--user", "1000:1000", container, "sh", "-c",
                       "test -n \"$(ls /home/dev/.claude/sessions/*.json 2>/dev/null)\""], check=False).returncode != 0:
                if time.monotonic() >= deadline:
                    raise RuntimeError("synthetic agent did not become ready")
                time.sleep(0.05)
            result = exec_in(container, ["agentville-collector", "--once"])
            verify(f"Collector {number} reached HQ through reverse SSH", "delivery failed" not in result.stderr)
            roster = json.loads(exec_in(container, ["cat", "/state/agentville/roster.json"]).stdout)
            verify(f"Collector {number} observed the real process", len(roster) == 1 and roster[0]["on_duty"])
            verify(f"Collector {number} resolved the Git Project", roster[0]["project_id"] == "github.com/example/agentville-test")
            identity = config["host"]["id"], roster[0]["agent_id"]
            if saved is None:
                saved = identity
            else:
                verify("Branch and colleague identity survive container recreation", identity == saved)
            if number == 1:
                for repetition in (1, 2):
                    before = store.totals.accepted
                    launched = exec_in(container, ["sh", "-c",
                        "nohup agentville-collector > /state/agentville/collector.log 2>&1 < /dev/null & printf '%s\\n' \"$!\""])
                    pid = int(launched.stdout.strip())
                    deadline = time.monotonic() + 10
                    while store.totals.accepted <= before and time.monotonic() < deadline:
                        time.sleep(0.05)
                    verify(f"nohup Collector run {repetition} delivered", store.totals.accepted > before)
                    command = exec_in(container, ["cat", f"/proc/{pid}/cmdline"]).stdout
                    verify(f"nohup Collector run {repetition} process identity", "agentville-collector" in command)
                    identity_receipt = exec_in(container, ["ps", "-p", str(pid), "-o", "pid,lstart,args"])
                    verify(f"nohup Collector run {repetition} start time receipt", "agentville-collector" in identity_receipt.stdout)
                    exec_in(container, ["kill", "-TERM", str(pid)])
                    deadline = time.monotonic() + 10
                    while True:
                        stat = run(["docker", "exec", "--user", "1000:1000", container, "cat", f"/proc/{pid}/stat"], check=False)
                        if stat.returncode or stat.stdout[stat.stdout.rfind(")") + 2:].startswith("Z "):
                            break
                        if time.monotonic() >= deadline:
                            raise RuntimeError("Collector did not stop")
                        time.sleep(0.05)
                tunnel.terminate()
                tunnel.wait(timeout=10)
                run(["docker", "stop", container])
        bridge = prefix + "-bridge"
        run(["docker", "run", "-d", "--name", bridge, "--add-host", "host.docker.internal:host-gateway",
             *mounts, *env, image, "sleep", "infinity"])
        containers.append(bridge)
        exec_in(bridge, ["git", "init", "-q", "/workspace/agentville"])
        exec_in(bridge, ["git", "remote", "add", "origin", "https://github.com/example/agentville-test.git"])
        failed = exec_in(bridge, ["agentville-collector", "--once"])
        verify("bridge loopback does not reach the host tunnel", "delivery failed" in failed.stderr)
        run(["docker", "cp", str(key), bridge + ":/tmp/test_key"])
        exec_in(bridge, ["chown", "1000:1000", "/tmp/test_key"], user="0")
        run(["docker", "exec", "-d", "--user", "1000:1000", bridge, "ssh", "-N", "-i", "/tmp/test_key",
             "-p", str(ssh_port), "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
             "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/tmp/known_hosts",
             "-L", f"127.0.0.1:{forward_port}:127.0.0.1:{forward_port}", "dev@host.docker.internal"])
        deadline = time.monotonic() + 10
        while True:
            probe = run(["docker", "exec", bridge, "python", "-c",
                         f"import socket; socket.create_connection(('127.0.0.1',{forward_port}),timeout=1).close()"], check=False)
            if probe.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("gateway SSH tunnel did not become ready")
            time.sleep(0.1)
        run(["docker", "exec", "-d", "--user", "1000:1000", bridge, "python", "/verification/agent.py"])
        deadline = time.monotonic() + 10
        while run(["docker", "exec", bridge, "sh", "-c",
                   "test -n \"$(ls /home/dev/.claude/sessions/*.json 2>/dev/null)\""], check=False).returncode:
            if time.monotonic() >= deadline:
                raise RuntimeError("bridge synthetic agent did not become ready")
            time.sleep(0.05)
        result = exec_in(bridge, ["agentville-collector", "--once"])
        verify("bridge Collector reaches HQ through host-gateway SSH", "delivery failed" not in result.stderr)
        roster = json.loads(exec_in(bridge, ["cat", "/state/agentville/roster.json"]).stdout)
        verify("bridge Collector keeps the persisted colleague identity", len(roster) == 1 and roster[0]["agent_id"] == saved[1] and roster[0]["on_duty"])
        print(f"Results: {workspace / 'results.json'}", flush=True)
    finally:
        for tunnel in tunnels:
            if tunnel.poll() is None:
                tunnel.terminate()
                tunnel.wait(timeout=10)
        for container in containers:
            run(["docker", "stop", container], check=False)
        if server is not None:
            server.should_exit = True
        if server_thread is not None:
            server_thread.join(timeout=10)
        receipts.close()


if __name__ == "__main__":
    main()
