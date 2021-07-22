import getpass
import os
import sys
from pathlib import Path

import pytest

from publisher import config
from tests.test_upload import write_manifest


def write_config(tmp_path, **kwargs):
    lines = []
    for name, value in kwargs.items():
        lines.append(f"{name} = {repr(value)}")
    cfg = tmp_path / "osrelease_config.py"
    cfg.write_text("\n".join(lines))
    print("\n".join(lines))
    return {"OSRELEASE_CONFIG": str(cfg)}


@pytest.fixture
def default_config(tmp_path, monkeypatch):
    env = write_config(
        tmp_path,
        BACKEND_TOKEN="token",
        PRIVATE_REPO_ACCESS_TOKEN="private",
        ALLOWED_USERS={getpass.getuser(): "github-user"},
    )
    monkeypatch.setitem(os.environ, "OSRELEASE_CONFIG", env["OSRELEASE_CONFIG"])
    return env


def test_config_osrelease_config_env_var(tmp_path):
    cfg = tmp_path / "osrelease_config.py"
    cfg.write_text("FOO=1")
    env = {"OSRELEASE_CONFIG": str(cfg)}
    assert config.get_config(env) == {"FOO": 1}


def test_config_file_cwd(tmp_path):
    cfg = tmp_path / "osrelease_config.py"
    cfg.write_text("FOO=1")
    current = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert config.get_config({}) == {"FOO": 1}
    finally:
        os.chdir(current)


def test_config_file_venv(tmp_path):
    cfg = tmp_path / "osrelease_config.py"
    cfg.write_text("FOO=1")
    env = {"VIRTUAL_ENV": str(tmp_path)}
    assert config.get_config(env) == {"FOO": 1}


def test_config_file_module(tmp_path, monkeypatch):
    cfg = tmp_path / "osrelease_config.py"
    executable = tmp_path / "bin" / "python"
    monkeypatch.setattr(sys, "executable", str(executable))
    cfg.write_text("FOO=1")
    assert config.get_config({}) == {"FOO": 1}


def test_get_current_user(monkeypatch):
    real_user = getpass.getuser()

    monkeypatch.setattr("publisher.config.getpass.getuser", lambda: "user")
    assert config.get_current_user() == "user"

    if "GITHUB_ACTIONS" not in os.environ:
        monkeypatch.setattr("publisher.config.getpass.getuser", lambda: "jobrunner")
        assert config.get_current_user() == real_user


def test_load_config_files_not_exist(options, tmp_path):
    write_manifest(tmp_path)
    options.files = ["notexist"]

    with pytest.raises(SystemExit) as exc_info:
        config.load_config(options, tmp_path)

    assert "Files do not exist: notexist" in str(exc_info.value)


def test_load_config_no_backend_token(options, tmp_path):
    write_manifest(tmp_path)
    env = write_config(
        tmp_path,
        PRIVATE_REPO_ACCESS_TOKEN="private",
        ALLOWED_USERS={getpass.getuser(): "github-user"},
    )
    f = tmp_path / "test.txt"
    f.write_text("test")
    options.files = [str(f)]

    with pytest.raises(SystemExit) as exc_info:
        config.load_config(options, tmp_path, env=env)

    assert "Could not load BACKEND_TOKEN" in str(exc_info.value)


def test_load_config_new_publish_no_files(options, default_config, tmp_path):
    write_manifest(tmp_path)
    options.new_publish = True

    with pytest.raises(SystemExit) as exc_info:
        config.load_config(options, tmp_path)

    assert "No files provided to release" in str(exc_info.value)


def test_load_config_old_publish_no_private_token(options, tmp_path):
    write_manifest(tmp_path)
    env = write_config(
        tmp_path,
        BACKEND_TOKEN="token",
        ALLOWED_USERS={getpass.getuser(): "github-user"},
    )

    with pytest.raises(SystemExit) as exc_info:
        config.load_config(options, tmp_path, env=env)

    assert "Could not load PRIVATE" in str(exc_info.value)


def test_load_config_old_publish_no_git(options, default_config, tmp_path):
    write_manifest(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        config.load_config(options, tmp_path)

    assert "No files provided to release" in str(exc_info.value)


def test_load_config_username_not_allowed(options, tmp_path, monkeypatch):
    write_manifest(tmp_path)
    env = write_config(
        tmp_path, BACKEND_TOKEN="token", PRIVATE_REPO_ACCESS_TOKEN="private"
    )
    f = tmp_path / "file.txt"
    f.write_text("test")
    options.files = [str(f)]
    monkeypatch.setattr("publisher.config.getpass.getuser", lambda: "user")

    with pytest.raises(SystemExit) as exc_info:
        config.load_config(options, tmp_path, env=env)

    assert "Only members of the core OpenSAFELY team" in str(exc_info.value)


def test_load_config_username_allowed_users_list_still_blocks(
    options, tmp_path, monkeypatch
):
    write_manifest(tmp_path)
    env = write_config(
        tmp_path,
        BACKEND_TOKEN="token",
        PRIVATE_REPO_ACCESS_TOKEN="private",
        ALLOWED_USERS=["validuser"],
    )
    f = tmp_path / "file.txt"
    f.write_text("test")
    options.files = [str(f)]
    monkeypatch.setattr("publisher.config.getpass.getuser", lambda: "invaliduser")

    with pytest.raises(SystemExit) as exc_info:
        config.load_config(options, tmp_path, env=env)

    assert "Only members of the core OpenSAFELY team" in str(exc_info.value)


def test_load_config_new_publish(options, tmp_path, default_config):
    write_manifest(tmp_path)
    f = tmp_path / "file.txt"
    f.write_text("test")
    options.files = [str(f)]
    options.new_publish = True

    files, cfg = config.load_config(options, tmp_path)
    assert files == [f]
    assert cfg == {
        "backend_token": "token",
        "private_token": "private",
        "study_repo_url": "repo",
        "workspace": "workspace",
        "username": "github-user",
        "commit_message": f"Released from {tmp_path} by github-user",
    }


def test_load_config_new_publish_dirs(options, tmp_path, default_config):
    write_manifest(tmp_path)
    d = tmp_path / "dir"
    d.mkdir()
    f1 = d / "file1.txt"
    f1.write_text("test")
    f2 = d / "file2.txt"
    f2.write_text("test")
    options.files = [str(d)]
    options.new_publish = True

    files, cfg = config.load_config(options, tmp_path)
    assert list(sorted(files)) == [f1, f2]
    assert cfg == {
        "backend_token": "token",
        "private_token": "private",
        "study_repo_url": "repo",
        "workspace": "workspace",
        "username": "github-user",
        "commit_message": f"Released from {tmp_path} by github-user",
    }


def test_load_config_old_publish_with_files(options, tmp_path, default_config):
    write_manifest(tmp_path)
    f = tmp_path / "file.txt"
    f.write_text("test")
    options.files = [str(f)]

    files, cfg = config.load_config(options, tmp_path)
    assert files == [f]
    assert cfg == {
        "backend_token": "token",
        "private_token": "private",
        "study_repo_url": "repo",
        "workspace": "workspace",
        "username": "github-user",
        "commit_message": f"Released from {tmp_path} by github-user",
    }


def test_load_config_old_publish_with_git(
    options, tmp_path, default_config, release_repo
):
    os.chdir(release_repo.name)
    rpath = Path(release_repo.name)

    write_manifest(rpath)
    f = tmp_path / "file.txt"
    f.write_text("test")

    files, cfg = config.load_config(options, rpath)
    assert files == [Path("a/b/committed.txt")]
    assert cfg == {
        "backend_token": "token",
        "private_token": "private",
        "study_repo_url": "repo",
        "workspace": "workspace",
        "username": "github-user",
        "commit_message": f"Released from {rpath} by github-user",
    }
