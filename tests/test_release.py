import getpass
import json
import logging
import os
import pathlib
import subprocess

from publisher.release import (RedactingStreamHandler, find_manifest,
                               get_current_user, get_files, main)

# Fixtures for these tests:
#
# a `release_repo` contains one file with two commits, one never-committed but
# staged file, and one unstaged file
#
# a `study_repo` is an empty git repo


def test_successful_push_message(capsys, release_repo, study_repo):
    os.chdir(release_repo.name)
    main(study_repo_url=study_repo.name, token="", files=get_files())
    captured = capsys.readouterr()

    assert captured.out.startswith("Pushed new changes")


def test_release_repo_master_branch_unchanged(release_repo, study_repo):
    os.chdir(release_repo.name)
    main(study_repo_url=study_repo.name, token="", files=get_files())
    os.chdir(study_repo.name)
    committed = pathlib.Path("released_outputs/a/b/committed.txt")
    staged = pathlib.Path("released_outputs/a/b/staged.txt")
    unstaged = pathlib.Path("released_outputs/a/b/unstaged.txt")
    assert not committed.exists()
    assert not staged.exists()
    assert not unstaged.exists()


def test_release_repo_release_branch_changed(release_repo, study_repo):
    os.chdir(release_repo.name)
    main(study_repo_url=study_repo.name, token="", files=get_files())
    os.chdir(study_repo.name)
    subprocess.check_output(["git", "checkout", "release-candidates"])

    committed = pathlib.Path("released_outputs/a/b/committed.txt")
    staged = pathlib.Path("released_outputs/a/b/staged.txt")
    unstaged = pathlib.Path("released_outputs/a/b/unstaged.txt")
    assert committed.exists()
    assert committed.read_text() == "a redacted change"
    assert not staged.exists()
    assert not unstaged.exists()


def test_release_repo_commit_history(release_repo, study_repo):
    os.chdir(release_repo.name)
    main(study_repo_url=study_repo.name, token="", files=get_files())
    os.chdir(study_repo.name)
    log = subprocess.check_output(["git", "log", "--all"], encoding="utf8")
    assert "second commit" in log
    assert "first commit" not in log

    search = subprocess.check_output(
        ["git", "log", "--all", "-Sunredacted"], encoding="utf8"
    )
    assert search == ""


def test_noop_message(capsys, release_repo, study_repo):
    os.chdir(release_repo.name)
    main(study_repo_url=study_repo.name, token="", files=get_files())
    main(study_repo_url=study_repo.name, token="", files=get_files())
    captured = capsys.readouterr()
    assert captured.out.splitlines()[-1] == "Nothing to do!"


def test_find_manifest(tmp_path):
    manifest_path = tmp_path / "metadata" / "manifest.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text(json.dumps({"repo": "url"}))
    workdir = tmp_path / "release"
    workdir.mkdir()
    assert find_manifest(workdir) == {"repo": "url"}


def test_find_manifest_not_found(tmp_path):
    workdir = tmp_path / "release"
    workdir.mkdir()
    assert find_manifest(workdir) is None


def test_redacting_logger(capsys):

    logger = logging.getLogger(__name__ + ".test_redacting_logger")
    logger.setLevel(logging.DEBUG)
    ch = RedactingStreamHandler()
    ch.setLevel(logging.DEBUG)
    logger.addHandler(ch)
    logger.info("https://token@github-proxy.opensafely.org")


    _, err = capsys.readouterr()

    assert err == "https://xxxxxx@github-proxy.opensafely.org\n"


def test_get_current_user(monkeypatch):
    real_user = getpass.getuser()

    monkeypatch.setattr('publisher.release.getpass.getuser', lambda: "user")
    assert get_current_user() == "user"


    if 'GITHUB_ACTIONS' not in os.environ:
        monkeypatch.setattr('publisher.release.getpass.getuser', lambda: "jobrunner")
        assert get_current_user() == real_user
    
