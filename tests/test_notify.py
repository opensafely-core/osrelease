import json
import os
from http import HTTPStatus

import pytest

import publisher
from publisher.notify import main

from .utils import UrlopenFixture


@pytest.fixture
def urlopen(monkeypatch):
    data = UrlopenFixture()
    monkeypatch.setattr(publisher.notify, "urlopen", data.urlopen)
    return data


def test_main_success(urlopen):
    urlopen.set_response(
        HTTPStatus.CREATED,
        headers={
            "Location": "/location",
        },
    )

    main("token", "testuser", "/path/to/outputs", ["output/file.txt"])

    JOB_SERVER = os.environ.get("JOB_SERVER", "https://jobs.opensafely.org")
    assert urlopen.request.full_url == (f"{JOB_SERVER}/api/v2/release-notifications/")
    assert urlopen.request.headers["Authorization"] == "token"
    assert json.loads(urlopen.request.data.decode("utf8")) == {
        "created_by": "testuser",
        "path": "/path/to/outputs",
        "files": ["output/file.txt"],
    }


def test_main_error_response(urlopen):
    urlopen.set_response(
        HTTPStatus.BAD_REQUEST,
        headers={"Content-Type": "application/json"},
        body=json.dumps({"detail": "ERROR MSG"}),
    )

    with pytest.raises(Exception) as exc_info:
        main("token", "testuser", "/path/to/outputs", ["file"])

    assert str(exc_info.value) == "Error: 400 response from the server: ERROR MSG"
