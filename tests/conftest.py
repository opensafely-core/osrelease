import os
import pathlib
import pytest
import shutil
import subprocess
import tempfile


def git_init():
    subprocess.check_call(["git", "init"])


@pytest.fixture(scope="function", autouse=True)
def setup_env(monkeypatch):
    """Set up config required to do commits
    """
    d = tempfile.mkdtemp()
    os.chdir(d)
    monkeypatch.setenv("HOME", d)

    subprocess.check_call(
        ["git", "config", "--global", "user.email", "test@example.com"]
    )
    subprocess.check_call(["git", "config", "--global", "user.name", "test"])
    yield
    shutil.rmtree(d)


@pytest.fixture
def release_repo():
    """Create a working folder which is a git repo, containing committed, staged and unstaged files
    """
    d = tempfile.TemporaryDirectory()
    os.chdir(d.name)
    git_init()

    committed = pathlib.Path("a/b/committed.txt")
    staged = pathlib.Path("a/b/staged.txt")
    unstaged = pathlib.Path("a/b/unstaged.txt")
    for f in [committed, staged, unstaged]:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.touch()
    committed.write_text("an unredacted change")
    subprocess.check_call(["git", "add", committed])

    subprocess.check_call(["git", "commit", "-m", "first commit"])
    committed.write_text("a redacted change")
    subprocess.check_call(["git", "add", committed])
    subprocess.check_call(["git", "commit", "-m", "second commit"])

    subprocess.check_call(["git", "add", staged])
    return d


@pytest.fixture
def study_repo():
    d = tempfile.TemporaryDirectory()
    os.chdir(d.name)
    git_init()
    return d

