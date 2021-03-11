import json
import os
import pathlib
import subprocess

from publisher.release import find_manifest, get_files, get_private_token, main

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


def test_get_private_token(tmp_path):
    token_path = tmp_path / "token"
    token_path.write_text("file token", "utf8")
    assert get_private_token({}) is None
    assert get_private_token({"PRIVATE_REPO_ACCESS_TOKEN": "env token"}) == "env token"
    assert get_private_token({"PRIVATE_TOKEN_PATH": str(token_path)}) == "file token"
    assert get_private_token({"PRIVATE_TOKEN_PATH": "/notexist"}) is None
    assert (
        get_private_token(
            {
                "PRIVATE_REPO_ACCESS_TOKEN": "env token",
                "PRIVATE_TOKEN_PATH": str(token_path),
            }
        )
        == "env token"
    )


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
