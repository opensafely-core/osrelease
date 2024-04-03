import getpass
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# 32MB max upload
MAX_SIZE = 32 * 1024 * 1024
LEVEL4_FILE_TYPES = set(
    [
        # tables
        ".csv",
        # images
        ".jpg",
        ".jpeg",
        ".png",
        ".svg",
        ".svgz",
        # reports
        ".html",
        ".pdf",
        ".txt",
        ".log",
        ".json",
        ".md",
    ]
)


def check_workplace_status(workspace_name):
    res = requests.get(
        f"https://jobs.opensafely.org/api/v2/workspaces/{workspace_name}/status"
    )
    if res.status_code == 500:
        sys.exit(f"Error: {res.status_code} response from {res.url}: Job Server down")
    elif res.status_code != 200:
        sys.exit(
            f"Error: {res.status_code} response from {res.url}: {res.json()['detail']}"
        )
    else:
        return res.json()["uses_new_release_flow"]


def get_config_file(env, filename="osrelease_config.py"):
    """Lookup possible config.py file locations.

    We do this so we can centrally configure an osrelease installation w/o
    needing users to have specific environment variables set.
    """
    lookup = [
        # explicit env var
        Path(env.get("OSRELEASE_CONFIG", "doesnotexist.osrelease")),
        # current dir
        Path(os.getcwd()) / filename,
        # explicit virtualenv directory
        Path(env.get("VIRTUAL_ENV", "doesnotexist.osrelease")) / filename,
        # implicit virtualenv directory, assuming argv[0] is the entrypoint in
        # $VIRTUALENV/bin/osrelease
        Path(sys.executable).parent.parent / filename,
        # backend install
        Path("/srv/osrelease/environ/osrelease_config.py"),
    ]

    for path in lookup:
        if path.exists():
            return path


def get_config(env=os.environ):
    config = {}
    config_file = get_config_file(env)
    if config_file:
        exec(config_file.read_text(), {}, config)
    return config


def get_current_user():
    # this works for windows and linux users
    username = getpass.getuser()

    # due to current permissions in linux backends, we have to release as the shared jobrunner user.
    # to preserve audit, use logname(1) to get the real user connected to the tty
    if username == "jobrunner":
        try:
            username = subprocess.check_output(["logname"], text=True).strip()
        except subprocess.CalledProcessError:
            # logname doesn't work in GH actions where it's in an interactive shell with a tty.
            pass

    return username


def find_manifest(path):
    manifest_path = path / "metadata/manifest.json"
    manifest = None
    if manifest_path.exists():
        try:
            manifest = json.load(manifest_path.open())
        except json.JSONDecodeError as exc:
            raise Exception(f"Could not load metadata/manifest.json - {exc}")

    if manifest is not None:
        if "repo" not in manifest:
            raise Exception(f"Invalid manifest {manifest_path} - no repo")
        if "workspace" not in manifest:
            raise Exception(f"Invalid manifest {manifest_path} - no workspace")

    return manifest


def ensure_git_config():
    try:
        subprocess.check_output(["git", "config", "--global", "user.name"])
        subprocess.check_output(["git", "config", "--global", "user.email"])
    except subprocess.CalledProcessError:
        logger.info(
            "You need to tell git who you are by running:\n\n"
            'git config --global user.name "YOUR NAME"\n'
            'git config --global user.email "YOUR EMAIL"'
        )


def load_config(options, release_dir, env=os.environ):

    cfg = get_config(env=env)
    manifest = find_manifest(release_dir)
    if manifest is None:
        sys.exit(
            "Could not find metadata/manifest.json - are you in a workspace directory?"
        )

    allowed_usernames = cfg.get("ALLOWED_USERS", {})
    if isinstance(allowed_usernames, list):
        allowed_usernames = {u: u for u in allowed_usernames}

    local_username = get_current_user()
    github_username = allowed_usernames.get(local_username, None)

    if github_username is None:
        sys.exit(
            f"We do not know who {local_username} is in Github. "
            f"Please ask tech-support to add the correct Github username for user {local_username} in the osrelease configuration.\n"
            "Note: this does not give you permission to release anything, but is a required first step."
        )

    workspace = manifest["workspace"]
    backend_token = cfg.get("BACKEND_TOKEN")
    config = {
        "backend": cfg.get("BACKEND", "unknown"),
        "backend_token": backend_token,
        "private_token": cfg.get("PRIVATE_REPO_ACCESS_TOKEN"),
        "api_server": cfg.get("API_SERVER", "http://127.0.0.1:8001"),
        "study_repo_url": manifest["repo"],
        "workspace": workspace,
        "username": github_username,
        "commit_message": f"Released from {release_dir} by {github_username}",
    }

    if options.github_publish:
        ensure_git_config()
        private_token = cfg.get("PRIVATE_REPO_ACCESS_TOKEN")
        if not private_token:
            sys.exit(
                "No PRIVATE_REPO_ACCESS_TOKEN env var set to enable github publish"
            )
    elif options.new_publish is None:
        # user has specified neither --gh or -n - check what the default is for this workspace.
        uses_new_flow = check_workplace_status(workspace)
        if not uses_new_flow:
            print(
                "Warning: this workspace is configured to use github releases by default, but this\n"
                "method is no longer allowed, so releasing to jobs.opensafely.org instead.\n"
                "To remove this warning, or if you really really do need to release to github, contact tech-support"
            )

    if not config["backend_token"]:
        sys.exit("Could not load BACKEND_TOKEN from config")

    return config


def get_files(options, cfg):
    files = []

    # check if the first file is a path to a release, and set release if so
    if not options.release and options.files:
        first = Path(options.files[0])
        if first.parts[0] == "releases" and len(first.parts) == 2:
            options.release = first.parts[1]
            options.files = options.files[1:]

    if options.release:
        # upload files to an exisiting release
        # avoid circular import
        from publisher import schema, upload

        workspace_url, auth_token = upload.get_auth(cfg)
        release_url = f"{workspace_url}/release/{options.release}"
        response, body = upload.release_hatch("GET", release_url, None, auth_token)
        index = schema.FileList(**json.loads(body))

        if options.files:
            errors = []
            for f in options.files:
                metadata = index.get(f)
                if metadata is None:
                    errors.append(
                        f"Could not find file {f} in release {options.release}"
                    )

            if errors:
                sys.exit("\n".join(errors))

            files = options.files
        else:
            files = [f.name for f in index.files]
    else:
        # release and upload files in one step, check paths locally
        for f in options.files:
            path = Path(f)
            if path.is_dir():
                files.extend(f for f in path.glob("**/*") if f.is_file())
            else:
                files.append(path)

        not_exist = [p for p in files if not p.exists()]
        if not_exist:
            filelist = "\n".join(str(s) for s in not_exist)
            sys.exit(f"Files do not exist:\n{filelist}")

        too_large = [p for p in files if p.stat().st_size > MAX_SIZE]
        if too_large:
            filelist = "\n".join(str(s) for s in too_large)
            sys.exit(f"Files are too large to release:\n{filelist}")

        bad_files = [p for p in files if p.suffix not in LEVEL4_FILE_TYPES]
        if bad_files:
            filelist = "\n".join(str(s) for s in bad_files)
            sys.exit(f"These files are not allowed to be released:\n{filelist}")


    if not files:
        sys.exit("No files provided to release")

    return files
