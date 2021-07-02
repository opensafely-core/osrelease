import getpass
import hashlib
import io
import json
import os
import urllib.error
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile


# this hashing method should be kept consistent with job-server
def hash_files(release_dir, files):
    # use md5 because its fast, and we only care about uniqueness, not security
    hash = hashlib.md5()
    # sort for consistency
    for filename in sorted(files):
        path = release_dir / filename
        hash.update(path.read_bytes())
    return hash.hexdigest()


# for testing
JOB_SERVER = os.environ.get("JOB_SERVER", "https://jobs.opensafely.org")


def main(release_dir, files, workspace, token):
    # include the manifest in the release
    files.append(Path("metadata/manifest.json"))
    release_hash = hash_files(release_dir, files)

    zip_buffer = io.BytesIO()
    with ZipFile(zip_buffer, "w") as zip_file:
        for path in files:
            zip_file.write(release_dir / path, arcname=str(path))

    data = zip_buffer.getvalue()
    request = Request(
        url=f"{JOB_SERVER}/api/v2/workspaces/{workspace}/releases/{release_hash}",
        method="PUT",
        data=data,
        headers={
            "Accept": "application/json",  # only for errors format
            "Content-Length": len(data),
            "Content-Type": "application/zip",
            "Content-Disposition": "attachment; filename=release.zip",
            "Authorization": token,
            "Backend-User": getpass.getuser(),
        },
    )

    try:
        response = urlopen(request)
    except urllib.error.HTTPError as exc:
        # HTTPErrors can be treated as HTTPResponse
        response = exc

    if response.status in (201, 303):
        location = response.headers["Location"]
        verb = "created" if response.status == 201 else "already uploaded"
        print(f"Release {verb} at {location}")
        return

    error_msg = response.read().decode("utf8")

    # try get more helpful error message
    if response.headers["Content-Type"] == "application/json":
        try:
            error_msg = json.loads(error_msg)["detail"]
        except Exception:
            pass

    raise Exception(f"Error: {response.status} response from the server: {error_msg}")
