import logging
import shutil
import socket
import subprocess
import tempfile
import os
import urllib
import urllib.parse

from pathlib import Path

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
logger.addHandler(ch)


def add_github_auth_to_repo(repo):
    """Add Basic HTTP Auth to a Github repo, from the environment.

    For example, `https://github.com/sebbacon/test.git` becomes `https:/<access_token>@github.com/sebbacon/test.git`
    """
    parts = urllib.parse.urlparse(repo)
    assert not parts.username and not parts.password
    return urllib.parse.urlunparse(
        parts._replace(
            netloc=f"{os.environ['PRIVATE_REPO_ACCESS_TOKEN']}@{parts.netloc}"
        )
    )


def run(cmd):
    logger.info("Running `%s`", " ".join(cmd))
    result = subprocess.run(cmd, encoding="utf8", capture_output=True)
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
        path = path.relative_to(subdir)
        depth = len(path.parts) - 1
        spacer = "  " * depth
        if path.is_file():
            lines.append(f"{spacer}* [{path}]({path})")
        elif path.is_dir():
            lines.append(f"{spacer}* {path}")
    if lines:
        return "# Table of contents\n\n" + "\n".join(lines)
    else:
        return None


def main():
    # List all files that are committed in the latest version
    files = [
        (os.path.abspath(x), x)
        for x in subprocess.check_output(
            ["git", "ls-files"], encoding="utf8"
        ).splitlines()
    ]
    last_commit_message = subprocess.check_output(
        ["git", "log", "-1", "--pretty=%B"], encoding="utf8"
    ).strip()
    release_branch = "release-candidates"
    release_subdir = Path("released_outputs")
    current_dir = os.getcwd()
    with tempfile.TemporaryDirectory() as d:
        os.chdir(d)
        repo_url = input(
            "Provide a Github URL for the repo to publish to (e.g. `https://github.com/opensafely/households-research/`):"
        )
        repo_url = "https://github.com/sebbacon/test-publisher.git"
        repo_url_with_pat = add_github_auth_to_repo(repo_url)
        run(["git", "clone", repo_url_with_pat, "repo"])  # XXX shallow?

        logger.debug(f"Checked out {repo_url_with_pat} to repo/")
        os.chdir("repo")
        checked_out = run(["git", "checkout", release_branch])
        if checked_out != 0:
            run(["git", "-b", "checkout", release_branch])
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
            run(["git", "add", "--all"])
            trailer = f"Opensafely-released-from: {socket.getfqdn()}:{current_dir} "
            commit_returncode = run(
                ["git", "commit", "-m", f"{last_commit_message}\n\n{trailer}"]
            )
            if commit_returncode == 0:
                run(["git", "push", "-f", "--set-upstream", "origin", release_branch])
                print(
                    f"Pushed new changes. Open a PR at `{repo_url.replace('.git', '')}/compare/{release_branch}`"
                )
            else:
                print("Nothing to do!")
        else:
            print("Local repo is empty!")


if __name__ == "__main__":
    main()
