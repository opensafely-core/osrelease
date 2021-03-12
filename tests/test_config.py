import json
import os
import pathlib
import subprocess

import publisher.config
from publisher.config import (
    get_config,
    get_private_github_token,
)



def test_config_file_cwd(tmp_path):
    config = tmp_path / "osrelease_config.py"
    config.write_text("FOO=1")
    current = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert get_config({}) == {"FOO": 1}
    finally:
        os.chdir(current)


def test_config_file_venv(tmp_path):
    config = tmp_path / "osrelease_config.py"
    config.write_text("FOO=1")
    env = {"VIRTUAL_ENV": str(tmp_path)}
    assert get_config(env) == {"FOO": 1}


def test_config_file_module(tmp_path, monkeypatch):
    config = tmp_path / "osrelease_config.py"
    config.write_text("FOO=1")
    monkeypatch.setattr(publisher.config, '__file__', str(tmp_path / 'config.py') )
    assert get_config({}) == {"FOO": 1}


def test_get_private_github_token(tmp_path):
    config = tmp_path / "osrelease_config.py"
    config.write_text("PRIVATE_REPO_ACCESS_TOKEN='token'")
    env = {"VIRTUAL_ENV": str(tmp_path)}
    assert get_private_github_token(env) == "token"
