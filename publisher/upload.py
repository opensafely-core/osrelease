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


class UploadTooLarge(UploadException):
    pass


class AlreadyUploaded(UploadException):
    pass


def main(files, cfg):
    release_id = create_release(files, cfg)
    upload_to_release(files, release_id, cfg)


def get_auth(cfg):
    workspace_url = f"{cfg['api_server']}/workspace/{cfg['workspace']}"
    auth_token = get_token(workspace_url, cfg["username"], cfg["backend_token"])
    return workspace_url, auth_token


def create_release(files, cfg, skip_github=True):
    workspace_url, auth_token = get_auth(cfg)

    index_url = workspace_url + "/current"
    response, body = release_hatch("GET", index_url, None, auth_token)
    index = FileList(**json.loads(body))
    filelist = FileList(files=[], metadata={"tool": "osrelease"})

    for f in files:
        filedata = index.get(f)
        if filedata is None:
            # shouldn't happen, as we've just verified it exists, but best be careful
            sys.exit(f"cannot find file {f}")
        filedata.metadata = {"tool": "osrelease"}
        filelist.files.append(filedata)

    release_create_url = workspace_url + "/release"

    headers = {}
    if skip_github:
        headers["Suppress-Github-Issue"] = "true"

    try:
        response, _ = release_hatch(
            "POST", release_create_url, filelist.json(), auth_token, headers,
        )
    except Forbidden:
        raise UploadException(
            f"User {cfg['username']} does not have permission to create a release"
        )

    release_id = response.headers["Release-Id"]
    logger.info(f"Release {release_id} created with {len(files)} files.")

    return release_id


def upload_to_release(files, release_id, cfg):
    workspace_url, auth_token = get_auth(cfg)
    release_url = f"{workspace_url}/release/{release_id}"
    try:
        for f in files:
            release_file = ReleaseFile(name=f)
            logger.info(f" - uploading {f}...")
            try:
                release_hatch("POST", release_url, release_file.json(), auth_token)
            except UploadTooLarge:
                logger.info(f"   - file too large")
            except AlreadyUploaded:
                logger.info(f"   - already uploaded")

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


def release_hatch(method, url, data, auth_token, headers=None):
    logger.debug(f"{method} {url}: {data}")
    if headers is None:
        headers = {}
    headers.update({
        "Accept": "application/json",
        "Authorization": auth_token,
    })
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

    # try get more helpful error message
    if response.headers["Content-Type"] == "application/json":
        try:
            body = json.loads(body)["detail"]
        except Exception:
            pass

    # handle exceptions we understand
    if response.status == 403:
        raise Forbidden()

    if response.status == 413:
        raise UploadTooLarge()

    if response.status == 400 and "already been uploaded" in body:
        raise AlreadyUploaded()
         
    # dunno what it is, raise
    raise UploadException(f"Error: {response.status} response from the server: {body}")
