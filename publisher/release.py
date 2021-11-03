import argparse
import getpass
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

from . import config, notify

GITHUB_PROXY_DOMAIN = "github-proxy.opensafely.org"


logger = logging.getLogger(__name__)

logging_defaults = {
    "user": getpass.getuser(),
    "workspace": os.getcwd(),
}


def record_with_defaults(*args, **kwargs):
    record = logging.LogRecord(*args, **kwargs)
    record.__dict__.update(logging_defaults)
    return record


def configure_logging():
    root = logging.getLogger()
    # ensure the root logger processes every log message - we'll filter with
    # handlers
    root.setLevel(logging.NOTSET)

    # info level logs go straight to the user using the default format, but
    # redacted
    user_output = RedactingStreamHandler()
    user_output.setLevel(logging.INFO)
    root.addHandler(user_output)

    logfile = os.environ.get("LOGFILE")
    if logfile:
        # add user and workspace dir to LogRecords
        logging.setLogRecordFactory(record_with_defaults)
        # now we can use them in formatting our log message
        formatter = logging.Formatter(
            fmt="{asctime} '{message}' user={user} dir={workspace}",
            datefmt="%Y-%m-%d %H:%M:%S",
            style="{",
        )
        # use utc time
        formatter.convertor = time.gmtime
        file_handler = logging.FileHandler(logfile)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)


class RedactingStreamHandler(logging.StreamHandler):
    def emit(self, record):
        record.msg = re.sub(r"(.*://).+@", r"\1xxxxxx@", record.msg)
        super().emit(record)


def get_authenticated_repo_url(repo, token, user, backend):
    """Convert raw https github repo url into something we can use.

    Validates it is a clean github.com url to prevent leaking creds elsewhere.

    Switches to using the configured proxy url rather than github.com

    Adds the supplied PAT token as basic auth. We abuse the fact that github
    ignores the basic auth username to include some useful info to help us
    debug proxy issues.

    Example:

    `https://github.com/sebbacon/test.git` becomes
    `https://osrelease-$BACKEND-$USER:$TOKEN@github-proxy.opensafely.org/sebbacon/test.git`
    """
    if "github.com" in repo:
        parts = urllib.parse.urlparse(repo)
        assert not parts.username and not parts.password
        repo = urllib.parse.urlunparse(
            parts._replace(
                netloc=f"osrelease-{backend}-{user}:{token}@{GITHUB_PROXY_DOMAIN}"
            )
        )
    return repo


def run_cmd(cmd, raise_exc=True, output_failure=True):
    logger.info("Running `%s`", " ".join(cmd))
    result = subprocess.run(cmd, encoding="utf8", capture_output=True)
    if raise_exc:
        result.check_returncode()
    if result.returncode != 0 and output_failure:
        logger.warning(
            "Error %s: %s\n%s\n-------", result.returncode, result.stdout, result.stderr
        )
    return result.returncode


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


def main(study_repo_url, token, files, commit_msg, user, backend):
    release_branch = "release-candidates"
    release_subdir = Path("released_outputs")
    workspace_dir = Path(os.getcwd())
    released = False
    with tempfile.TemporaryDirectory() as d:
        try:
            os.chdir(d)

            study_repo_url_with_pat = get_authenticated_repo_url(
                study_repo_url, token, user, backend
            )
            try:
                run_cmd(["git", "clone", study_repo_url_with_pat, "repo"])
            except subprocess.CalledProcessError as exc:
                logger.debug(exc_info=True)
                if exc.stdout:
                    logger.debug(exc.stdout)
                if exc.stderr:
                    logger.debug(exc.stderr)
                raise RuntimeError(
                    f"Unable to clone {study_repo_url} via {GITHUB_PROXY_DOMAIN}"
                )

            logger.debug(f"Checked out {study_repo_url} to repo/")
            os.chdir("repo")
            checked_out = run_cmd(
                ["git", "checkout", release_branch],
                raise_exc=False,
                output_failure=False,
            )
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
                    logger.info(
                        "Pushed new changes. Open a PR at "
                        f"`{study_repo_url.replace('.git', '')}/compare/{release_branch}`"
                    )
                    released = True
                else:
                    logger.info("Nothing to do!")
            else:
                logger.info("Local repo is empty!")
        finally:
            # ensure we do not maintain an open handle on the temp dir, or else
            # the clean up fails
            os.chdir(workspace_dir)

        return released


def release(options, release_dir):
    try:
        files, cfg = config.load_config(options, release_dir)

        if not options.yes:
            logger.info("\n".join(str(f) for f in files))
            print()
            if (
                input("The above files will be published. Continue? (y/N)").lower()
                != "y"
            ):
                sys.exit()

        if options.new_publish:
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
                cfg["username"],
                cfg["backend"],
            )

            if released:
                notify.main(
                    cfg["backend_token"],
                    cfg["username"],
                    release_dir,
                    files,
                )

    except Exception as exc:
        logger.debug(exc_info=True)
        if exc.stdout:
            logger.debug(exc.stdout)
        if exc.stderr:
            logger.debug(exc.stderr)
        if options.verbose > 0:
            raise
        sys.exit(exc)


parser = argparse.ArgumentParser()
parser.add_argument("--verbose", "-v", action="count", default=0)
parser.add_argument("--yes", "-y", action="store_true")
parser.add_argument("--new-publish", "-n", action="store_true")
parser.add_argument("files", nargs="*")


def run():
    configure_logging()
    options = parser.parse_args()
    release(options, Path(os.getcwd()))


if __name__ == "__main__":
    run()
