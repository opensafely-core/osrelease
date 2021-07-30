import getpass
import json
import os
import subprocess
import sys
from pathlib import Path


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


def git_files(git_dir):
    old = os.getcwd()
    try:
        os.chdir(git_dir)
        return [
            Path(x)
            for x in subprocess.check_output(
                ["git", "ls-tree", "-r", "HEAD", "--name-only"], encoding="utf8"
            ).splitlines()
        ]
    finally:
        os.chdir(old)


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
        print(
            "You need to tell git who you are by running:\n\n"
            'git config --global user.name "YOUR NAME"\n'
            'git config --global user.email "YOUR EMAIL"'
        )


def load_config(options, release_dir, env=os.environ):
    ensure_git_config()

    cfg = get_config(env=env)
    manifest = find_manifest(release_dir)
    if manifest is None:
        sys.exit(
            "Could not find metadata/manifest.json - are you in a workspace directory?"
        )

    files = []
    for f in options.files:
        path = Path(f)
        if path.is_dir():
            files.extend(f for f in path.glob("**/*") if f.is_file())
        else:
            files.append(path)

    not_exist = [p for p in files if not p.exists()]
    if not_exist:
        filelist = ", ".join(str(s) for s in not_exist)
        sys.exit(f"Files do not exist: {filelist}")

    allowed_usernames = cfg.get("ALLOWED_USERS", {})
    if isinstance(allowed_usernames, list):
        allowed_usernames = {u: u for u in allowed_usernames}

    local_username = get_current_user()
    github_username = allowed_usernames.get(local_username, None)

    if github_username is None:
        # we do not know who they are
        if options.new_publish:
            sys.exit("You are not in the configured list of users to use osrelease.")
        else:
            sys.exit(
                "Only members of the core OpenSAFELY team can publish outputs. "
                "Please email disclosurecontrol@opensafely.org to request a release.\n"
            )

    config = {
        "backend_token": cfg.get("BACKEND_TOKEN"),
        "private_token": cfg.get("PRIVATE_REPO_ACCESS_TOKEN"),
        "api_server": cfg.get("API_SERVER", "http://127.0.0.1:8001"),
        "study_repo_url": manifest["repo"],
        "workspace": manifest["workspace"],
        "username": github_username,
        "commit_message": f"Released from {release_dir} by {github_username}",
    }

    if not config["backend_token"]:
        sys.exit("Could not load BACKEND_TOKEN from config")

    if options.new_publish:
        # must provide files in new publish
        if not files:
            sys.exit("No files provided to release")
    else:
        # deprecated github publishing
        if not config["private_token"]:
            sys.exit("Could not load PRIVATE_REPO_ACCESS_TOKEN token from config file")

        if not files:
            if Path(".git").exists():
                print("Found git repo, using deprecated git release flow.")
                files = git_files(release_dir)
            else:
                sys.exit("No files provided to release")

    return files, config
