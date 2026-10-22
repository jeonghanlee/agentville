import os

from agentville.collector.adapters.claude import _default_is_alive, proc_start_ticks


def _write_stat(root, pid, comm, start):
    fields = ["S"] + [str(i) for i in range(4, 22)] + [str(start)] + ["0"] * 30
    path = root / str(pid)
    path.mkdir(parents=True)
    (path / "stat").write_text(f"{pid} ({comm}) " + " ".join(fields) + "\n")


def test_proc_start_ticks_reads_field_22(tmp_path):
    _write_stat(tmp_path, 4242, "claude", 987654)
    assert proc_start_ticks(4242, str(tmp_path)) == "987654"


def test_proc_start_ticks_handles_spaces_and_parens_in_comm(tmp_path):
    _write_stat(tmp_path, 4243, "a (b) c", 123)
    assert proc_start_ticks(4243, str(tmp_path)) == "123"


def test_proc_start_ticks_missing_process(tmp_path):
    assert proc_start_ticks(1, str(tmp_path)) is None


def test_default_is_alive_matches_own_process():
    pid = os.getpid()
    ticks = proc_start_ticks(pid)
    assert ticks is not None
    assert _default_is_alive(pid, ticks)
    assert not _default_is_alive(pid, str(int(ticks) + 1))
