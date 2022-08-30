import hashlib
import io
import json
import os
from http import HTTPStatus
from pathlib import Path
from zipfile import ZipFile

import pytest

from publisher import schema, signing, upload


@pytest.fixture
def workspace_files(tmp_path):
    """Create a set of test files to release."""
    # same inputs as job-server test
    files = {
        "foo.txt": "foo",
        "dir/bar.txt": "bar",
        "outputs/data.csv": "data",
    }

    for name, contents in files.items():
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_text(contents)

    cwd = os.getcwd()
    os.chdir(tmp_path)

    # get the os files so that we tests proper windows paths
    yield [p.relative_to(tmp_path) for p in tmp_path.glob("**/*") if p.is_file()]

    os.chdir(cwd)


@pytest.fixture
def cfg():
    return {
        "workspace": "workspace",
        "backend_token": "token" * 10,
        "username": "user",
        "api_server": "http://hatch",
    }


def test_main_forbidden(workspace, urlopen, cfg):
    workspace.add_urlopen_index(urlopen)

    urlopen.add_response(HTTPStatus.FORBIDDEN)

    with pytest.raises(upload.UploadException) as exc:
        upload.main(workspace.files, cfg)

    assert "User user does not have permission" in str(exc.value)


def test_main_success_no_upload_permission(workspace, urlopen, cfg):
    workspace.write("foo.txt", "foo")
    workspace.write("dir/bar.txt", "bar")
    workspace.write("outputs/data.csv", "data")

    workspace.add_urlopen_index(urlopen)
    urlopen.add_response(HTTPStatus.CREATED, headers={"Release-Id": "test_release_id"})
    urlopen.add_response(HTTPStatus.FORBIDDEN)

    upload.main(workspace.files, cfg)

    request1 = urlopen.requests[1]
    assert request1.full_url == "http://hatch/workspace/workspace/release"
    files = json.loads(request1.data)["files"]
    assert sorted(f["name"] for f in files) == list(
        sorted(["foo.txt", "dir/bar.txt", "outputs/data.csv"])
    )

    request2 = urlopen.requests[2]
    assert (
        request2.full_url == "http://hatch/workspace/workspace/release/test_release_id"
    )


def test_main_success(workspace, urlopen, cfg):
    workspace.write("dir/bar.txt", "bar")
    workspace.write("foo.txt", "foo")
    workspace.write("outputs/data.csv", "data")

    workspace.add_urlopen_index(urlopen)

    urlopen.add_response(HTTPStatus.CREATED, headers={"Release-Id": "test_release_id"})
    urlopen.add_response(HTTPStatus.CREATED)
    urlopen.add_response(HTTPStatus.CREATED)
    urlopen.add_response(HTTPStatus.CREATED)
    backend_token = "token" * 10

    upload.main(workspace.files, cfg)

    request = urlopen.requests[1]
    assert request.full_url == "http://hatch/workspace/workspace/release"
    token = signing.AuthToken.verify(
        request.headers["Authorization"], backend_token, salt="hatch"
    )
    filelist = schema.FileList(**json.loads(request.data))
    assert filelist.metadata == {"tool": "osrelease"}
    assert filelist.files[0].name == "dir/bar.txt"
    assert filelist.files[0].metadata == {"tool": "osrelease"}
    for f, r in zip(workspace.files, urlopen.requests[2:]):
        normalized_path = str(f).replace("\\", "/")
        assert json.loads(r.data) == {"name": normalized_path}
    assert request.headers["Suppress-github-issue"] == "true"
