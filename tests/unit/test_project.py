import pytest

from agentville.collector.project import COMMON_OFFICE, GitProjectResolver, local_project_id, normalize_remote


@pytest.mark.parametrize(
    "url",
    [
        "git@github.com:jeonghanlee/agentville.git",
        "https://github.com/jeonghanlee/agentville",
        "https://user@github.com/jeonghanlee/agentville.git",
        "https://user:p@ss@github.com/jeonghanlee/agentville.git",
        "ssh://git@github.com:22/jeonghanlee/agentville.git",
        "https://GitHub.com/jeonghanlee/agentville/",
    ],
)
def test_normalize_remote_forms(url):
    assert normalize_remote(url) == "github.com/jeonghanlee/agentville"


def test_normalize_remote_rejects_local_path():
    assert normalize_remote("/srv/git/repo.git") is None


def test_resolver_outside_repository_is_common_office(tmp_path):
    assert GitProjectResolver("host-a").resolve(str(tmp_path)) == COMMON_OFFICE


def test_local_project_id_is_stable_and_host_scoped():
    assert local_project_id("h1", "/r") == local_project_id("h1", "/r")
    assert local_project_id("h1", "/r") != local_project_id("h2", "/r")
