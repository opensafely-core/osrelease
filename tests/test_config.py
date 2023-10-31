import getpass
import json
import os
import sys
from pathlib import Path

import pytest
import responses

from publisher import config


@pytest.yield_fixture
def old_release_flow():
    with responses.RequestsMock() as response:
        response.add(
            responses.GET,
            "https://jobs.opensafely.org/api/v2/workspaces/workspace/status",
            json={"uses_new_release_flow": False},
            status=200,
        )
        yield response


@pytest.yield_fixture
def new_release_flow():
    with responses.RequestsMock() as response:
        response.add(
            responses.GET,
            "https://jobs.opensafely.org/api/v2/workspaces/workspace/status",
            json={"uses_new_release_flow": True},
            status=200,
        )
        yield response


def write_config(tmp_path, **kwargs):
    lines = []
    for name, value in kwargs.items():
        lines.append(f"{name} = {repr(value)}")
    cfg = tmp_path / "osrelease_config.py"
    cfg.write_text("\n".join(lines))
    print("\n".join(lines))
    return {"OSRELEASE_CONFIG": str(cfg)}


def write_manifest(release_dir, workspace="workspace", repo="repo", **kwargs):
    manifest = {"workspace": workspace, "repo": repo}
    manifest.update(kwargs)
    manifest_path = Path("metadata") / "manifest.json"
    actual_path = release_dir / manifest_path
    actual_path.parent.mkdir()
    actual_path.write_text(json.dumps(manifest))
    return manifest


@pytest.fixture
def default_config(tmp_path, monkeypatch):
    env = write_config(
        tmp_path,
        BACKEND="test",
        BACKEND_TOKEN="token" * 10,
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


def test_config_file_venv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "osrelease_config.py"
    cfg.write_text("FOO=1")
    env = {"VIRTUAL_ENV": str(tmp_path)}
    assert config.get_config(env) == {"FOO": 1}


def test_config_file_module(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
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


def test_check_status(new_release_flow):
    new_workflow = config.check_workplace_status("workspace")
    assert new_workflow is True


@responses.activate
def test_check_status_down():
    responses.add(
        responses.GET,
        "https://jobs.opensafely.org/api/v2/workspaces/test_workspace/status",
        json={"detail": "Not found. "},
        status=500,
    )

    with pytest.raises(SystemExit) as exc_info:
        config.check_workplace_status("test_workspace")

    assert "Error: 500 response" in str(exc_info.value)


def test_load_config_no_backend_token(options, tmp_path, new_release_flow):
    write_manifest(tmp_path)
    env = write_config(
        tmp_path,
        ALLOWED_USERS={getpass.getuser(): "github-user"},
    )
    f = tmp_path / "test.txt"
    f.write_text("test")
    options.files = [str(f)]

    with pytest.raises(SystemExit) as exc_info:
        config.load_config(options, tmp_path, env=env)

    assert "Could not load BACKEND_TOKEN" in str(exc_info.value)


def test_load_config_old_publish_no_private_token(options, tmp_path):
    write_manifest(tmp_path)
    options.github_publish = True
    env = write_config(
        tmp_path,
        BACKEND_TOKEN="token",
        ALLOWED_USERS={getpass.getuser(): "github-user"},
    )

    with pytest.raises(SystemExit) as exc_info:
        config.load_config(options, tmp_path, env=env)

    assert "No PRIVATE_REPO_ACCESS_TOKEN env var" in str(exc_info.value)


def test_load_config_username_not_allowed(options, tmp_path, monkeypatch):
    write_manifest(tmp_path)
    env = write_config(
        tmp_path,
        BACKEND_TOKEN="token",
    )
    f = tmp_path / "file.txt"
    f.write_text("test")
    options.files = [str(f)]
    monkeypatch.setattr("publisher.config.getpass.getuser", lambda: "invaliduser")

    with pytest.raises(SystemExit) as exc_info:
        config.load_config(options, tmp_path, env=env)

    assert "invaliduser" in str(exc_info.value)


def test_load_config_username_allowed_users_list_still_blocks(
    options, tmp_path, monkeypatch
):
    write_manifest(tmp_path)
    env = write_config(
        tmp_path,
        BACKEND_TOKEN="token",
        ALLOWED_USERS=["validuser"],
    )
    f = tmp_path / "file.txt"
    f.write_text("test")
    options.files = [str(f)]
    monkeypatch.setattr("publisher.config.getpass.getuser", lambda: "invaliduser")

    with pytest.raises(SystemExit) as exc_info:
        config.load_config(options, tmp_path, env=env)

    assert "invaliduser" in str(exc_info.value)


def test_load_config_new_publish_as_arg(options, tmp_path, default_config):
    write_manifest(tmp_path)
    options.new_publish = True

    cfg = config.load_config(options, tmp_path)
    assert cfg == {
        "api_server": "http://127.0.0.1:8001",
        "backend": "test",
        "backend_token": "token" * 10,
        "private_token": None,
        "study_repo_url": "repo",
        "workspace": "workspace",
        "username": "github-user",
        "commit_message": f"Released from {tmp_path} by github-user",
    }


def test_load_config_new_publish_as_api_call(options, tmp_path, default_config):
    options.new_publish = False
    write_manifest(tmp_path)

    # options.new_publish overruled by API call to job server
    cfg = config.load_config(options, tmp_path)
    assert cfg == {
        "api_server": "http://127.0.0.1:8001",
        "backend": "test",
        "backend_token": "token" * 10,
        "private_token": None,
        "study_repo_url": "repo",
        "workspace": "workspace",
        "username": "github-user",
        "commit_message": f"Released from {tmp_path} by github-user",
    }


@responses.activate
def test_load_config_new_publish_job_server_down(options, tmp_path, default_config):
    responses.add(
        responses.GET,
        "https://jobs.opensafely.org/api/v2/workspaces/workspace/status",
        json={"detail": "Test Error"},
        status=500,
    )
    write_manifest(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        config.load_config(options, tmp_path)

    assert "Job Server down" in str(exc_info.value)


def test_get_files_new_dirs(options, tmp_path, default_config):
    write_manifest(tmp_path)
    d = tmp_path / "dir"
    d.mkdir()
    f1 = d / "file1.txt"
    f1.write_text("test")
    f2 = d / "file2.txt"
    f2.write_text("test")
    options.files = [str(d)]
    options.new_publish = True

    cfg = config.load_config(options, tmp_path)
    files = config.get_files(options, cfg)
    assert list(sorted(files)) == [f1, f2]


def test_get_files_no_files(options, default_config, tmp_path):
    write_manifest(tmp_path)
    options.new_publish = True

    cfg = config.load_config(options, tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        config.get_files(options, cfg)

    assert "No files provided to release" in str(exc_info.value)


def test_get_files_not_exist(options, tmp_path, default_config):
    write_manifest(tmp_path)
    options.files = ["notexist"]
    options.new_publish = True

    cfg = config.load_config(options, tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        config.get_files(options, cfg)

    assert "Files do not exist:\nnotexist" in str(exc_info.value)


def test_get_files_too_large(options, tmp_path, default_config, monkeypatch):
    write_manifest(tmp_path)
    f = tmp_path / "file1.txt"
    f.write_text("test" * 100)
    monkeypatch.setattr(config, "MAX_SIZE", 100)

    options.files = [str(f)]
    options.new_publish = True

    cfg = config.load_config(options, tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        config.get_files(options, cfg)

    assert f"Files are too large to release:\n{f}" in str(exc_info.value)


def test_get_files_release_no_files(options, workspace, urlopen, default_config):

    release = workspace.create_release("release_id")
    release.add_urlopen_index(urlopen)
    options.new_publish = True
    options.release = release.id

    cfg = config.load_config(options, workspace.path)

    with pytest.raises(SystemExit) as exc_info:
        config.get_files(options, cfg)

    assert "No files" in str(exc_info.value)


def test_get_files_release_all_files(options, workspace, urlopen, default_config):
    release = workspace.create_release("release_id")
    release.write("foo.txt", "foo")
    release.write("bar.txt", "bar")
    release.add_urlopen_index(urlopen)
    options.new_publish = True
    options.release = release.id

    cfg = config.load_config(options, workspace.path)

    assert config.get_files(options, cfg) == ["bar.txt", "foo.txt"]


def test_get_files_release_subset_files(options, workspace, urlopen, default_config):
    release = workspace.create_release("release_id")
    release.write("foo.txt", "foo")
    release.write("bar.txt", "bar")
    release.add_urlopen_index(urlopen)
    options.new_publish = True
    options.release = release.id
    options.files = ["foo.txt"]

    cfg = config.load_config(options, workspace.path)

    assert config.get_files(options, cfg) == ["foo.txt"]


def test_get_files_release_path(options, workspace, urlopen, default_config):
    release = workspace.create_release("release_id")
    release.write("foo.txt", "foo")
    release.write("bar.txt", "bar")
    release.add_urlopen_index(urlopen)
    options.new_publish = True
    options.files = ["releases/release_id", "foo.txt"]

    cfg = config.load_config(options, workspace.path)
    assert config.get_files(options, cfg) == ["foo.txt"]
    assert options.release == "release_id"
    assert options.files == ["foo.txt"]
