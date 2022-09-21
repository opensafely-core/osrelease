import hashlib
import json
import subprocess
from http import HTTPStatus

import pytest

from publisher import release, schema, upload
from tests import utils


def git_init():
    subprocess.check_call(["git", "init"])


@pytest.fixture
def options():
    return release.parser.parse_args([])


@pytest.fixture
def urlopen(monkeypatch):
    data = utils.UrlopenFixture()
    monkeypatch.setattr(upload, "urlopen", data.urlopen)
    return data


class Workspace:
    """Test workspace

    Assumes we are chdir'd into its path, which is done by the fixture itself.
    """

    def __init__(self, name, path):
        self.name = name
        self.path = path
        self.write_manifest()

    def write_manifest(self):
        manifest = {"workspace": self.name, "repo": "repo"}
        manifest_path = self.path / "metadata/manifest.json"
        manifest_path.parent.mkdir()
        manifest_path.write_text(json.dumps(manifest))
        return manifest

    def write(self, name, contents):
        path = self.path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        return path

    @property
    def files(self):
        """List all files in a directory recursively as a flat list.

        Sorted, and excluding various files
        """

        def exclude(path):
            return (
                any(p for p in path.parts if p.startswith("."))
                or path.parts[0] == "releases"
                or path.parts[0] == "metadata"
            )

        relative_paths = (
            p.relative_to(self.path) for p in self.path.glob("**/*") if p.is_file()
        )
        return list(sorted(filter(lambda p: not exclude(p), relative_paths)))

    def get_index(self):
        index = schema.FileList(files=[])
        for f in self.files:
            path = self.path / f
            index.files.append(
                schema.FileMetadata(
                    name=str(f),
                    size=path.stat().st_size,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    date=path.stat().st_mtime,
                )
            )

        return index

    def add_urlopen_index(self, urlopen):
        body = self.get_index().json()
        urlopen.add_response(HTTPStatus.OK, body=body)

    def create_release(self, release_id):
        return Release(release_id, self)


class Release(Workspace):
    def __init__(self, release_id, workspace):
        self.id = release_id
        self.workspace = workspace
        self.path = workspace.path / "releases" / release_id
        self.path.mkdir(parents=True)


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    name = "workspace"
    workspace_dir = tmp_path / name
    workspace_dir.mkdir()
    monkeypatch.chdir(workspace_dir)
    return Workspace(name, workspace_dir)
