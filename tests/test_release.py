import logging
import os
import subprocess
from pathlib import Path

import responses

import pytest

from publisher import config, release

# Fixtures for these tests:
#
# a `release_repo` contains one file with two commits, one never-committed but
# staged file, and one unstaged file
#
# a `study_repo` is an empty git repo


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


@responses.activate
def test_check_status():
    responses.add(
        responses.GET,
        "https://jobs.opensafely.org/api/v2/workspaces/test_workspace/status",
        json={"uses_new_release_flow": "True"},
        status=200,
    )

    new_workflow = release.check_status("test_workspace")
    assert new_workflow is True


@responses.activate
def test_check_status_down():
    responses.add(
        responses.GET,
        "https://jobs.opensafely.org/api/v2/workspaces/test_workspace/status",
        json={"error": "Bad Error"},
        status=404,
    )
    with pytest.raises(Exception) as e:
        release.check_status("test_workspace")

    assert str(e.value).startswith("404 Client Error")
