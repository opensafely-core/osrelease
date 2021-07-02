import io
import json
import os
from http import HTTPStatus
from pathlib import Path
from zipfile import ZipFile

import pytest

import publisher.upload
from publisher.upload import hash_files, main

from .utils import UrlopenFixture


@pytest.fixture
def release_dir(tmp_path):
    dirpath = tmp_path / "workspace"
    dirpath.mkdir()
    return dirpath


@pytest.fixture
def release_files(release_dir):
    """Create a set of test files to release."""
    # same inputs as job-server test
    files = {
        "foo.txt": "foo",
        "dir/bar.txt": "bar",
        "outputs/data.csv": "data",
    }

    for name, contents in files.items():
        path = release_dir / name
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_text(contents)

    return [Path(f) for f in files]


@pytest.fixture
def urlopen(monkeypatch):
    data = UrlopenFixture()
    monkeypatch.setattr(publisher.upload, "urlopen", data.urlopen)
    return data


def write_manifest(release_dir, workspace="workspace", repo="repo", **kwargs):
    manifest = {"workspace": workspace, "repo": repo}
    manifest.update(kwargs)
    manifest_path = Path("metadata") / "manifest.json"
    actual_path = release_dir / manifest_path
    actual_path.parent.mkdir()
    actual_path.write_text(json.dumps(manifest))
    return manifest


# this uses the same input data and hash as the test in job-server
def test_hash_files(release_dir, release_files):
    assert hash_files(release_dir, release_files) == "6c52ca16d696574e6ab5ece283eb3f3d"


# hash for realised files + test manifest.json


def test_main_success(release_dir, release_files, urlopen, capsys):
    urlopen.set_response(
        HTTPStatus.CREATED,
        headers={
            "Location": "/location",
        },
    )
    write_manifest(release_dir, workspace="workspace")
    # the hash for these test files + manifest contents
    release_hash = "d30535e1a8f6d000f1ed1a58ba5b9af1"

    main(release_dir, release_files, "workspace", "token")

    JOB_SERVER = os.environ.get("JOB_SERVER", "https://jobs.opensafely.org")
    assert urlopen.request.full_url == (
        f"{JOB_SERVER}/api/v2/workspaces/workspace/releases/{release_hash}"
    )
    assert urlopen.request.headers["Authorization"] == "token"

    # check the zip file matches expectations
    with ZipFile(io.BytesIO(urlopen.request.data)) as zf:
        for path in release_files:
            assert zf.read(str(path)) == (release_dir / path).read_bytes()

    out, err = capsys.readouterr()
    assert out == "Release created at /location\n"


def test_main_redirect(release_dir, release_files, urlopen, capsys):
    urlopen.set_response(
        HTTPStatus.SEE_OTHER,
        headers={
            "Location": "/location",
        },
    )
    write_manifest(release_dir, workspace="workspace")

    main(release_dir, release_files, "workspace", "token")

    out, err = capsys.readouterr()
    assert out == "Release already uploaded at /location\n"


def test_main_error_response(release_dir, release_files, urlopen, capsys):
    urlopen.set_response(
        HTTPStatus.BAD_REQUEST,
        headers={"Content-Type": "application/json"},
        body=json.dumps({"detail": "ERROR MSG"}),
    )
    manifest = write_manifest(release_dir, workspace="workspace")

    with pytest.raises(Exception) as exc_info:
        main(release_dir, release_files, manifest, "token")

    assert str(exc_info.value) == "Error: 400 response from the server: ERROR MSG"
