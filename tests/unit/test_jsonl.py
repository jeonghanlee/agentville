import os

from agentville.collector.jsonl import JsonlTail


def _records(tail):
    return [r for _, r in tail.read()]


def test_reads_only_complete_lines(tmp_path):
    path = tmp_path / "log.jsonl"
    path.write_bytes(b'{"a": 1}\n{"b": ')
    tail = JsonlTail(str(path))
    assert _records(tail) == [{"a": 1}]
    with open(path, "ab") as fh:
        fh.write(b'2}\n')
    assert _records(tail) == [{"b": 2}]
    assert _records(tail) == []


def test_restarts_on_truncation(tmp_path):
    path = tmp_path / "log.jsonl"
    path.write_text('{"a": 1}\n{"a": 2}\n')
    tail = JsonlTail(str(path))
    assert len(_records(tail)) == 2
    path.write_text('{"a": 3}\n')
    assert _records(tail) == [{"a": 3}]


def test_restarts_on_rotation(tmp_path):
    path = tmp_path / "log.jsonl"
    path.write_text('{"a": 1}\n')
    tail = JsonlTail(str(path))
    assert len(_records(tail)) == 1
    os.rename(path, tmp_path / "log.jsonl.1")
    path.write_text('{"a": 2}\n{"a": 3}\n')
    assert _records(tail) == [{"a": 2}, {"a": 3}]


def test_skips_malformed_lines_and_reports_offsets(tmp_path):
    path = tmp_path / "log.jsonl"
    path.write_text('not json\n{"a": 1}\n')
    tail = JsonlTail(str(path))
    assert list(tail.read()) == [(9, {"a": 1})]


def test_missing_file_yields_nothing(tmp_path):
    assert _records(JsonlTail(str(tmp_path / "absent.jsonl"))) == []
