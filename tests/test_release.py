import os
import pathlib
import subprocess

from publisher.release import main


def test_successful_push_message(capsys, release_repo, study_repo):
    os.chdir(release_repo.name)
    main(study_repo_url=study_repo.name)
    captured = capsys.readouterr()

    assert captured.out.startswith("Pushed new changes")


def test_release_repo_master_branch_unchanged(release_repo, study_repo):
    os.chdir(release_repo.name)
    main(study_repo_url=study_repo.name)
    os.chdir(study_repo.name)
    committed = pathlib.Path("released_outputs/a/b/committed.txt")
    staged = pathlib.Path("released_outputs/a/b/staged.txt")
    unstaged = pathlib.Path("released_outputs/a/b/unstaged.txt")
    assert not committed.exists()
    assert not staged.exists()
    assert not unstaged.exists()


def test_release_repo_release_branch_changed(release_repo, study_repo):
    os.chdir(release_repo.name)
    main(study_repo_url=study_repo.name)
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
    main(study_repo_url=study_repo.name)
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
    main(study_repo_url=study_repo.name)
    main(study_repo_url=study_repo.name)
    captured = capsys.readouterr()
    assert captured.out.splitlines()[-1] == "Nothing to do!"
