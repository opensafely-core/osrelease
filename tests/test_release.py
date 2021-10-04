import logging
import os
import subprocess
from pathlib import Path

import pytest


from publisher import config, release, upload
from .utils import UrlopenFixture

# Fixtures for these tests:
#
# a `release_repo` contains one file with two commits, one never-committed but
# staged file, and one unstaged file
#
# a `study_repo` is an empty git repo


@pytest.fixture
def urlopen(monkeypatch):
    data = UrlopenFixture()
    monkeypatch.setattr(upload, "urlopen", data.urlopen)
    return data


def test_successful_push_message(capsys, release_repo, study_repo):
    os.chdir(release_repo.name)
    files = config.git_files(Path(release_repo.name))
    release.main(
        study_repo_url=study_repo.name, token="", files=files, commit_msg="msg"
    )
    captured = capsys.readouterr()

    assert captured.out.startswith("Pushed new changes")


def test_release_repo_master_branch_unchanged(release_repo, study_repo):
    os.chdir(release_repo.name)
    files = config.git_files(Path(release_repo.name))
    release.main(
        study_repo_url=study_repo.name, token="", files=files, commit_msg="msg"
    )
    os.chdir(study_repo.name),
    committed = Path("released_outputs/a/b/committed.txt")
    staged = Path("released_outputs/a/b/staged.txt")
    unstaged = Path("released_outputs/a/b/unstaged.txt")
    assert not committed.exists()
    assert not staged.exists()
    assert not unstaged.exists()


def test_release_repo_release_branch_changed(release_repo, study_repo):
    os.chdir(release_repo.name)
    files = config.git_files(Path(release_repo.name))
    release.main(
        study_repo_url=study_repo.name, token="", files=files, commit_msg="msg"
    )
    os.chdir(study_repo.name)
    subprocess.check_output(["git", "checkout", "release-candidates"])

    committed = Path("released_outputs/a/b/committed.txt")
    staged = Path("released_outputs/a/b/staged.txt")
    unstaged = Path("released_outputs/a/b/unstaged.txt")
    assert committed.exists()
    assert committed.read_text() == "a redacted change"
    assert not staged.exists()
    assert not unstaged.exists()


def test_noop_message(capsys, release_repo, study_repo):
    os.chdir(release_repo.name)
    files = config.git_files(Path(release_repo.name))
    release.main(
        study_repo_url=study_repo.name, token="", files=files, commit_msg="msg"
    )
    release.main(
        study_repo_url=study_repo.name, token="", files=files, commit_msg="msg"
    )
    captured = capsys.readouterr()
    assert captured.out.splitlines()[-1] == "Nothing to do!"


def test_redacting_logger(capsys):

    logger = logging.getLogger(__name__ + ".test_redacting_logger")
    logger.setLevel(logging.DEBUG)
    ch = release.RedactingStreamHandler()
    ch.setLevel(logging.DEBUG)
    logger.addHandler(ch)
    logger.info("https://token@github-proxy.opensafely.org")

    _, err = capsys.readouterr()

    assert err == "https://xxxxxx@github-proxy.opensafely.org\n"


def test_releaseno_args(tmp_path):
    options = release.parser.parse_args([])
    with pytest.raises(SystemExit) as ctx:
        release.release(options, tmp_path)

    assert "Could not find metadata/manifest.json" in str(ctx.value)
