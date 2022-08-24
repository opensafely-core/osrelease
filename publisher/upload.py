import hashlib
import io
import json
import logging
import os
import sys
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from publisher.schema import FileList, FileMetadata, ReleaseFile
from publisher.signing import AuthToken

logger = logging.getLogger(__name__)


class UploadException(Exception):
    pass


class Forbidden(Exception):
    pass


def main(files, workspace, backend_token, user, api_server):
    workspace_url = f"{api_server}/workspace/{workspace}"
    auth_token = get_token(workspace_url, user, backend_token)

    response, body = release_hatch("GET", workspace_url, None, auth_token)
    index = FileList(**json.loads(body))
    filelist = FileList(files=[], metadata={"tool": "osrelease"})

    for f in files:
        filedata = index.get(f)
        if filedata is None:
            # shouldn't happen, as we've just verified it exists, but best be careful
            sys.exit(f"cannot find file {f}")

        filelist.files.append(filedata)

    release_create_url = workspace_url + "/release"

    try:
        response, _ = release_hatch(
            "POST", release_create_url, filelist.json(), auth_token
        )
    except Forbidden:
        raise UploadException(
            f"User {user} does not have permission to create a release"
        )

    release_id = response.headers["Release-Id"]
    release_url = response.headers["Location"]
    logger.info(f"Release {release_id} created with {len(files)} files.")

    try:
        for f in files:
            release_file = ReleaseFile(name=f)
            logger.info(f" - uploading {f}...")
            release_hatch("POST", release_url, release_file.json(), auth_token)
    except Forbidden:
        # they can create releases, but not upload them
        logger.info("permission denied")
        logger.info(
            f"You do not have permission to upload the requested files for Release {release_id}.\n"
            f"The OpenSAFELY review team will review your requested Release."
        )
    else:
        logger.info(f"Uploaded {len(files)} files for Release {release_id}")


def get_token(url, user, backend_token):
    token = AuthToken(
        url=url,
        user=user,
        expiry=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    return token.sign(backend_token, salt="hatch")


def release_hatch(method, url, data, auth_token):
    logger.debug(f"{method} {url}: {data}")
    headers = {
        "Accept": "application/json",
        "Authorization": auth_token,
    }
    if data:
        data = data.encode("utf8")
        headers["Content-Length"] = len(data)
        headers["Content-Type"] = "application/json"

    request = Request(
        url=url,
        method=method,
        data=data,
        headers=headers,
    )

    try:
        response = urlopen(request)
    except urllib.error.HTTPError as exc:
        # HTTPErrors can be treated as HTTPResponse
        response = exc

    body = response.read().decode("utf8")

    if response.status in (200, 201):
        return response, body

    if response.status == 403:
        raise Forbidden()

    # try get more helpful error message
    if response.headers["Content-Type"] == "application/json":
        try:
            body = json.loads(body)["detail"]
        except Exception:
            pass

    raise UploadException(f"Error: {response.status} response from the server: {body}")
