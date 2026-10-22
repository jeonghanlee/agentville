import socket
from importlib import metadata

import pytest
import uvicorn

import agentville
from agentville.collector import main as collector_main
from agentville.hq import main as hq_main
from agentville.hq.app import create_app
from agentville.hq.store import Store


@pytest.mark.parametrize("module, name", [(collector_main, "agentville-collector"), (hq_main, "agentville-hq")])
def test_version_option_prints_package_version(module, name, monkeypatch, capsys):
    monkeypatch.setattr(metadata, "version", lambda dist: "0.1.0")
    with pytest.raises(SystemExit) as exit_info:
        module.main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out == f"{name} 0.1.0\n"


def test_version_falls_back_when_not_installed(monkeypatch, tmp_path):
    def missing(dist):
        raise metadata.PackageNotFoundError(dist)

    monkeypatch.setattr(metadata, "version", missing)
    assert agentville.version() == "0.0.0"
    monkeypatch.setattr(metadata, "version", lambda dist: "0.1.0")
    assert create_app(Store(str(tmp_path / "hq.sqlite3"))).version == "0.1.0"


def _refused(main, argv, prefix, text):
    with pytest.raises(SystemExit) as exit_info:
        main(argv)
    message = exit_info.value.code
    assert isinstance(message, str) and message.startswith(prefix + ": ") and "\n" not in message, message
    assert text in message, message


@pytest.mark.parametrize("content, text", [
    ("host: [\n", "YAML syntax error at line 2"),
    ("- a\n", "must be a mapping"),
    ("host: x\n", "host must be a mapping"),
    ("host: {id: b}\nthresholds: x\n", "thresholds must be a mapping"),
    ("host: {id: b}\nthresholds: {phone: soon}\n", "thresholds.phone must be an integer"),
    ("host: {id: b}\ncollector: [1]\n", "collector must be a mapping"),
    ("host: {id: b}\ncollector: {poll_interval: 0}\n", "collector.poll_interval must be greater than 0"),
    ("host: {id: b}\ncollector: {poll_interval: often}\n", "collector.poll_interval must be a number"),
    ("host: {id: b}\ncollector: {heartbeat_interval: 0}\n", "collector.heartbeat_interval must be at least 1"),
    ("host: {id: b}\nproviders: x\n", "providers must be a mapping"),
    ("host: {id: b}\nproviders: {codex: x}\n", "providers.codex must be a list"),
    ("host: {id: b}\nhq: x\n", "hq must be a mapping"),
    ("host: {id: b}\nconditions: 5\n", "conditions must be a list"),
    ("host: {id: b}\naliases: {a: ''}\n", "aliases.a must be a non-empty string of at most 40 characters"),
])
def test_collector_reports_bad_configuration_in_one_line(tmp_path, content, text):
    path = tmp_path / "config.yaml"
    path.write_text(content)
    path.chmod(0o600)
    argv = ["--config", str(path), "--once", "--output", str(tmp_path / "out.jsonl")]
    _refused(collector_main.main, argv, "agentville-collector", text)


def test_collector_reports_unreadable_configuration(tmp_path):
    argv = ["--config", str(tmp_path), "--once", "--output", str(tmp_path / "out.jsonl")]
    _refused(collector_main.main, argv, "agentville-collector", f"configuration {tmp_path}: Is a directory")


def _private(path, content):
    path.write_text(content)
    path.chmod(0o600)
    return str(path)


def _hq(tmp_path, *options):
    return ["--db", str(tmp_path / "hq.sqlite3"), "--port", "0", *options]


def test_hq_reports_missing_or_malformed_token_files(tmp_path):
    missing = str(tmp_path / "missing")
    _refused(hq_main.main, _hq(tmp_path, "--tokens", missing), "agentville-hq", f"cannot read {missing}")
    _refused(hq_main.main, _hq(tmp_path, "--viewer-token-file", missing), "agentville-hq", f"cannot read {missing}")
    malformed = _private(tmp_path / "tokens.yaml", "b1: [\n")
    _refused(hq_main.main, _hq(tmp_path, "--tokens", malformed), "agentville-hq", "YAML syntax error at line 2")


def test_hq_validates_tls_files_before_start(tmp_path):
    cert, key = _private(tmp_path / "cert.pem", "not a certificate\n"), _private(tmp_path / "key.pem", "not a key\n")
    _refused(hq_main.main, _hq(tmp_path, "--tls-cert", cert, "--tls-key", key), "agentville-hq", "cannot load TLS certificate")
    missing = str(tmp_path / "missing.pem")
    _refused(hq_main.main, _hq(tmp_path, "--tls-cert", missing, "--tls-key", key), "agentville-hq", "cannot load TLS certificate")


def test_hq_reports_a_port_in_use(tmp_path):
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        argv = ["--db", str(tmp_path / "hq.sqlite3"), "--port", str(port)]
        _refused(hq_main.main, argv, "agentville-hq", f"cannot listen on 127.0.0.1:{port}: ")


def test_hq_announces_only_a_bound_socket(tmp_path, monkeypatch, capsys):
    served = []

    def run(server, sockets=None):
        served.append(sockets[0].getsockname())
        assert "serving" in capsys.readouterr().err

    monkeypatch.setattr(uvicorn.Server, "run", run)
    assert hq_main.main(_hq(tmp_path)) == 0
    assert served[0][0] == "127.0.0.1" and served[0][1] > 0


def test_hq_reports_an_unusable_database_path(tmp_path):
    (tmp_path / "file").write_text("")
    db = str(tmp_path / "file" / "hq.sqlite3")
    _refused(hq_main.main, ["--db", db, "--port", "0"], "agentville-hq", f"cannot open database {db}: ")
