import argparse
import json
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

from . import upload


class RedactingStreamHandler(logging.StreamHandler):
    def emit(self, record):
        record.msg = re.sub(r"(.*://)[a-z0-9]+", r"\1xxxxxx", record.msg)
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
        repo = urllib.parse.urlunparse(parts._replace(netloc=f"{token}@{parts.netloc}"))
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


def get_files():
    return [
        Path(x)
        for x in subprocess.check_output(
            ["git", "ls-tree", "-r", "HEAD", "--name-only"], encoding="utf8"
        ).splitlines()
    ]


def main(study_repo_url, token, files):

    # List all files that are committed in the latest version
    last_commit_message = subprocess.check_output(
        ["git", "log", "-1", "--pretty=%B"], encoding="utf8"
    ).strip()
    release_branch = "release-candidates"
    release_subdir = Path("released_outputs")
    repo_dir = Path(os.getcwd())
    with tempfile.TemporaryDirectory() as d:
        try:
            os.chdir(d)

            study_repo_url_with_pat = add_github_auth_to_repo(study_repo_url, token)
            try:
                run_cmd(["git", "clone", study_repo_url_with_pat, "repo"])
            except subprocess.CalledProcessError:
                raise RuntimeError(f"Unable to clone {study_repo_url}")

            logger.debug(f"Checked out {study_repo_url} to repo/")
            os.chdir("repo")
            checked_out = run_cmd(["git", "checkout", release_branch], raise_exc=False)
            if checked_out != 0:
                run_cmd(["git", "checkout", "-b", release_branch])
            logger.debug("Copying files from current repo to the checked out one")
            for path in files:
                dst = release_subdir / path
                src = repo_dir / path
                dst.parent.mkdir(exist_ok=True, parents=True)
                logger.debug("Copied %s", src)
                shutil.copy(src, dst)

            index_markdown = make_index(release_subdir)
            if index_markdown:
                release_subdir.mkdir(parents=True, exist_ok=True)
                with open(release_subdir / "README.md", "w") as f:
                    f.write(index_markdown)
                run_cmd(["git", "add", "--all"])
                trailer = f"Opensafely-released-from: {socket.getfqdn()}:{repo_dir} "
                commit_returncode = run_cmd(
                    ["git", "commit", "-m", f"{last_commit_message}\n\n{trailer}"],
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
                else:
                    print("Nothing to do!")
            else:
                print("Local repo is empty!")
        finally:
            # ensure we do not maintain an open handle on the temp dir, or else
            # the clean up fails
            os.chdir(repo_dir)


def get_private_token(env=os.environ):
    private_token = env.get("PRIVATE_REPO_ACCESS_TOKEN")
    if private_token:
        return private_token.strip()

    token_path = env.get("PRIVATE_TOKEN_PATH")
    if token_path:
        try:
            private_token = Path(token_path).read_text().strip()
        except Exception:
            pass

    return private_token


def find_manifest(path):
    manifest_path = path / "metadata/manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.load(manifest_path.open())
        except json.JSONDecodeError:
            return None
        else:
            return manifest

    # we've reached the top
    if path.parent == path:
        return None

    # recurse upwards
    return find_manifest(path.parent)


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", "-v", action="count", default=0)
    parser.add_argument("--yes", "-t", action="store_true")
    parser.add_argument("--new-publish", "-n", action="store_true")
    parser.add_argument("study_repo_url", nargs="?")
    options = parser.parse_args()

    release_dir = Path(os.getcwd())
    manifest = find_manifest(release_dir)

    if manifest is None:
        sys.exit("Could not metadata/manifest.json - are you in a workspace directory?")

    if options.new_publish:
        backend_token = upload.get_backend_token()
        if not backend_token:
            sys.exit("Could not load authentication token")
    else:
        if options.study_repo_url:
            if not options.study_repo_url.startswith("https://github.com/opensafely/"):
                sys.exit("Invalid url: must start with https://github.com/opensafely/")
        else:
            options.study_repo_url = manifest["repo"]

        private_token = get_private_token()
        if not private_token:
            sys.exit(
                "Could not load private token from "
                "PRIVATE_REPO_ACCESS_TOKEN or PRIVATE_TOKEN_PATH"
            )

    files = get_files()

    if not options.yes:
        print("\n".join(str(f) for f in files))
        print()
        if input("The above files will be published. Continue? (y/N)").lower() != "y":
            sys.exit()

    try:
        if options.new_publish:
            sys.exit(
                upload.main(
                    release_dir,
                    files,
                    manifest,
                    backend_token,
                )
            )
        else:
            main(options.study_repo_url, private_token, files)
    except Exception as exc:
        if options.verbose > 0:
            raise
        sys.exit(exc)


if __name__ == "__main__":
    run()
