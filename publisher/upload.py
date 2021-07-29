import hashlib
import io
import json
import os
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from publisher.signing import AuthToken
from publisher.schema import Release, ReleaseFile, UrlFileName


class UploadException(Exception):
    pass


class Forbidden(Exception):
    pass


def main(files, workspace, backend_token, user, api_server):
    workspace_url = f"{api_server}/workspace/{workspace}"
    auth_token = get_token(workspace_url, user, backend_token)

    release_create_url = workspace_url + "/release"

    release = Release(
        files={UrlFileName(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    )

    try:
        response = do_post(release_create_url, release.json(), auth_token)
    except Forbidden:
        raise UploadException(
            f"User {user} does not have permission to create a release"
        )


    release_id = response.headers["Release-Id"]
    release_url = response.headers["Location"]
    print(f"Release {release_id} created with {len(files)} files.")

    try:
        for f in files:
            release_file = ReleaseFile(name=str(f))
            print(" - uploading {f}... ", end="")
            do_post(release_url, release_file.json(), auth_token)
            print("done")
    except Forbidden:
        # they can create releases, but not upload them
        print("permission denied")
        print(
            f"You do not have permission to upload the requested files for Release {release_id}.\n"
            f"The OpenSAFELY review team will review your requested Release."
        )
    else:
        print(f"Uploaded {len(files)} files for Release {release_id}")


def get_token(url, user, backend_token):
    token = AuthToken(
        url=url,
        user=user,
        expiry=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    return token.sign(backend_token, salt="hatch")


def do_post(url, data, auth_token):

    data = data.encode('utf8')
    request = Request(
        url=url,
        data=data,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Length": len(data),
            "Content-Type": "application/json",
            "Authorization": auth_token,
        },
    )

    try:
        response = urlopen(request)
    except urllib.error.HTTPError as exc:
        # HTTPErrors can be treated as HTTPResponse
        response = exc

    if response.status == 201:
        return response

    if response.status == 403:
        raise Forbidden()

    error_msg = response.read().decode("utf8")

    # try get more helpful error message
    if response.headers["Content-Type"] == "application/json":
        try:
            error_msg = json.loads(error_msg)["detail"]
        except Exception:
            pass

    raise UploadException(
        f"Error: {response.status} response from the server: {error_msg}"
    )
