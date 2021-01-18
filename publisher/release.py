import argparse
import logging
import os
import re
import shutil
import socket
import subprocess
import tempfile
import urllib
import urllib.parse
from pathlib import Path


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
        repo = urllib.parse.urlunparse(
            parts._replace(
                netloc=f"{token}@{parts.netloc}"
            )
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


def get_files():
    return [
        (os.path.abspath(x), x)
        for x in subprocess.check_output(
            ["git", "ls-tree", "-r", "HEAD", "--name-only"], encoding="utf8"
        ).splitlines()
    ]


def main(study_repo_url, token):

    # List all files that are committed in the latest version
    last_commit_message = subprocess.check_output(
        ["git", "log", "-1", "--pretty=%B"], encoding="utf8"
    ).strip()
    release_branch = "release-candidates"
    release_subdir = Path("released_outputs")
    current_dir = os.getcwd()
    files = get_files()
    with tempfile.TemporaryDirectory() as d:
        os.chdir(d)
        study_repo_url_with_pat = add_github_auth_to_repo(study_repo_url, token)
        try:
            run_cmd(["git", "clone", study_repo_url_with_pat, "repo"])
        except subprocess.CalledProcessError:
            raise RuntimeError(f"Unable to clone {study_repo_url}")

        logger.debug(f"Checked out {study_repo_url_with_pat} to repo/")
        os.chdir("repo")
        checked_out = run_cmd(["git", "checkout", release_branch], raise_exc=False)
        if checked_out != 0:
            run_cmd(["git", "checkout", "-b", release_branch])
        logger.debug("Copying files from current repo to the checked out one")
        for src, dst in files:
            dst = os.path.join(release_subdir, dst)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            logger.debug("Copied %s", src)
            shutil.copy(src, dst)
        index_markdown = make_index(release_subdir)
        if index_markdown:
            release_subdir.mkdir(parents=True, exist_ok=True)
            with open(release_subdir / "README.md", "w") as f:
                f.write(index_markdown)
            run_cmd(["git", "add", "--all"])
            trailer = f"Opensafely-released-from: {socket.getfqdn()}:{current_dir} "
            commit_returncode = run_cmd(
                ["git", "commit", "-m", f"{last_commit_message}\n\n{trailer}"],
                raise_exc=False,
            )

            if commit_returncode == 0:
                run_cmd(
                    ["git", "push", "-f", "--set-upstream", "origin", release_branch]
                )
                print(
                    "Pushed new changes. Open a PR at "
                    f"`{study_repo_url.replace('.git', '')}/compare/{release_branch}`"
                )
            else:
                print("Nothing to do!")
        else:
            print("Local repo is empty!")
        os.chdir(current_dir)


def get_private_token(env=os.environ):
    private_token = env.get('PRIVATE_REPO_ACCESS_TOKEN')
    if not private_token:
        token_path = env.get('PRIVATE_TOKEN_PATH')
        if token_path:
            try: 
                private_token = Path(token_path).read_text()
            except Exception:
                pass
    return private_token


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", "-v", action="count", default=0)
    parser.add_argument("--yes", "-t", action="store_true")
    parser.add_argument("study_repo_url")
    options = parser.parse_args()

    private_token = get_private_token()
    if not private_token:
        sys.exit(
            "Could not load private token from "
            "PRIVATE_REPO_ACCESS_TOKEN or PRIVATE_TOKEN_PATH"
        )

    cont = True
    if not options.yes:
        files = [x[1] for x in get_files()]
        print("\n".join(files))
        print()
        cont = input("The above files will be published. Continue? (y/N)") == "y"
    if cont:
        main(options.study_repo_url, private_token)


if __name__ == "__main__":
    run()
