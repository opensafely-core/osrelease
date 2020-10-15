import os
import pathlib
import pytest
import subprocess
import tempfile


@pytest.fixture
def release_repo():
    d = tempfile.TemporaryDirectory()
    os.chdir(d.name)
    subprocess.check_call(["git", "init"])
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
    subprocess.check_call(["git", "init"])
    return d
