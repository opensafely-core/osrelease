import json
import logging
import os
import urllib.error
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

JOB_SERVER = os.environ.get("JOB_SERVER", "https://jobs.opensafely.org")


def main(token, username, path, files):
    data = json.dumps(
        {
            "created_by": username,
            "path": str(path),
            "files": [str(f) for f in files],
        }
    ).encode("utf-8")

    request = Request(
        url=f"{JOB_SERVER}/api/v2/release-notifications/",
        data=data,
        method="POST",
        headers={
            "Accept": "application/json",  # only for errors format
            "Authorization": token,
            "Content-Type": "application/json",
        },
    )

    try:
        response = urlopen(request)
    except urllib.error.HTTPError as exc:
        # HTTPErrors can be treated as HTTPResponse
        response = exc

    if response.status == 201:
        logging.info("Notification sent")
        return

    error_msg = response.read().decode("utf8")

    # try get more helpful error message
    if response.headers["Content-Type"] == "application/json":
        try:
            error_msg = json.loads(error_msg)["detail"]
        except Exception:
            pass
    raise Exception(f"Error: {response.status} response from the server: {error_msg}")
