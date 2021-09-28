import argparse
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

import requests

from . import config, notify

GITHUB_PROXY_DOMAIN = "github-proxy.opensafely.org"


class RedactingStreamHandler(logging.StreamHandler):
    def emit(self, record):
        record.msg = re.sub(r"(.*://).+@", r"\1xxxxxx@", record.msg)
        super().emit(record)


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
ch = RedactingStreamHandler()
ch.setLevel(logging.DEBUG)
logger.addHandler(ch)


def add_github_auth_to_repo(repo, token):
    """Add Basic HTTP Auth to a Github repo, from the environment.

    For example, `https://github.com/sebbacon/test.git` becomes
    `https://<access_token>@github.com/sebbacon/test.git`
    """
    if "github.com" in repo:
        parts = urllib.parse.urlparse(repo)
        assert not parts.username and not parts.password
        repo = urllib.parse.urlunparse(
            parts._replace(netloc=f"{token}@{GITHUB_PROXY_DOMAIN}")
        )
    return repo


def run_cmd(cmd, raise_exc=True):
    logger.info("Running `%s`", " ".join(cmd))
    result = subprocess.run(cmd, encoding="utf8", capture_output=True)
    if raise_exc:
        result.check_returncode()
    if result.returncode != 0:
        logger.warning(
            "Error %s: %s\n%s\n-------", result.returncode, result.stdout, result.stderr
        )
    return result.returncode


def tree(directory):
    print(f"+ {directory}")
    for path in sorted(directory.rglob("*")):
        depth = len(path.relative_to(directory).parts)
        spacer = "    " * depth
        print(f"{spacer}+ {path.name}")


def make_index(subdir):
    lines = []
    for path in sorted(Path(subdir).rglob("*")):
        relpath = path.relative_to(subdir)

        if str(relpath) == "README.md":
            continue
        depth = len(relpath.parts) - 1
        spacer = "  " * depth
        urlpath = "/".join(relpath.parts)
        if path.is_file():
            lines.append(f"{spacer}* [{urlpath}]({urlpath})")
        elif path.is_dir():
            lines.append(f"{spacer}* {urlpath}")
    if lines:
        return "# Table of contents\n\n" + "\n".join(lines)
    else:
        return None


def main(study_repo_url, token, files, commit_msg):
    release_branch = "release-candidates"
    release_subdir = Path("released_outputs")
    workspace_dir = Path(os.getcwd())
    released = False
    with tempfile.TemporaryDirectory() as d:
        try:
            os.chdir(d)

            study_repo_url_with_pat = add_github_auth_to_repo(study_repo_url, token)
            try:
                run_cmd(["git", "clone", study_repo_url_with_pat, "repo"])
            except subprocess.CalledProcessError:
                raise RuntimeError(
                    f"Unable to clone {study_repo_url} via {GITHUB_PROXY_DOMAIN}"
                )

            logger.debug(f"Checked out {study_repo_url} to repo/")
            os.chdir("repo")
            checked_out = run_cmd(["git", "checkout", release_branch], raise_exc=False)
            if checked_out != 0:
                run_cmd(["git", "checkout", "-b", release_branch])
            logger.debug("Copying files from current repo to the checked out one")
            for path in files:
                dst = release_subdir / path
                src = workspace_dir / path
                dst.parent.mkdir(exist_ok=True, parents=True)
                logger.debug("Copied %s", src)
                shutil.copy(src, dst)

            index_markdown = make_index(release_subdir)
            if index_markdown:
                release_subdir.mkdir(parents=True, exist_ok=True)
                with open(release_subdir / "README.md", "w") as f:
                    f.write(index_markdown)
                run_cmd(["git", "add", "--all"])
                trailer = (
                    f"Opensafely-released-from: {socket.getfqdn()}:{workspace_dir} "
                )
                commit_returncode = run_cmd(
                    ["git", "commit", "-m", f"{commit_msg}\n\n{trailer}"],
                    raise_exc=False,
                )

                if commit_returncode == 0:
                    run_cmd(
                        [
                            "git",
                            "push",
                            "-f",
                            "--set-upstream",
                            "origin",
                            release_branch,
                        ]
                    )
                    print(
                        "Pushed new changes. Open a PR at "
                        f"`{study_repo_url.replace('.git', '')}/compare/{release_branch}`"
                    )
                    released = True
                else:
                    print("Nothing to do!")
            else:
                print("Local repo is empty!")
        finally:
            # ensure we do not maintain an open handle on the temp dir, or else
            # the clean up fails
            os.chdir(workspace_dir)

        return released


def release(options, release_dir):
    try:
        files, cfg = config.load_config(options, release_dir)

        if not options.yes:
            print("\n".join(str(f) for f in files))
            print()
            if (
                input("The above files will be published. Continue? (y/N)").lower()
                != "y"
            ):
                sys.exit()

        res = requests.get(
            f"https://jobs.opensafely.org/api/v2/workspaces/{cfg['workspace']}/status"
        )
        uses_new_workflow = res.json()

        if options.new_publish or uses_new_workflow["uses_new_release_flow"]:
            # defer loading temporarily as it has dependencies that are not in
            # place in prod
            from publisher import upload

            released = upload.main(
                files,
                cfg["workspace"],
                cfg["backend_token"],
                cfg["username"],
                cfg["api_server"],
            )
        else:
            released = main(
                cfg["study_repo_url"],
                cfg["private_token"],
                files,
                cfg["commit_message"],
            )

            if released:
                notify.main(
                    cfg["backend_token"],
                    cfg["username"],
                    str(release_dir),
                    [f.relative_to(release_dir) for f in files],
                )

    except Exception as exc:
        if options.verbose > 0:
            raise
        sys.exit(exc)


parser = argparse.ArgumentParser()
parser.add_argument("--verbose", "-v", action="count", default=0)
parser.add_argument("--yes", "-t", action="store_true")
parser.add_argument("--new-publish", "-n", action="store_true")
parser.add_argument("files", nargs="*")


def run():
    options = parser.parse_args()
    release(options, Path(os.getcwd()))


if __name__ == "__main__":
    run()
