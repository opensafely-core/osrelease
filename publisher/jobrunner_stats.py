import argparse
import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from . import config
from .release import RedactingStreamHandler, add_github_auth_to_repo, run_cmd

GITHUB_PROXY_DOMAIN = "github-proxy.opensafely.org"


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
ch = RedactingStreamHandler()
ch.setLevel(logging.DEBUG)
logger.addHandler(ch)


def main(current_dir, job_runner_dir, days_to_extract, repo_url, branch, token):
    extracted = False
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d")
    since = now - timedelta(days=days_to_extract)
    since_timestamp = since.strftime("%Y-%m-%d")
    commit_message = f"Upload extracted stats from {since_timestamp} to {timestamp}"

    # Checkout the extraction repo to a temporary directory and extract the file to the
    # downloads folder
    with tempfile.TemporaryDirectory() as d:
        try:
            os.chdir(d)
            study_repo_url_with_pat = add_github_auth_to_repo(repo_url, token)
            try:
                run_cmd(["git", "clone", study_repo_url_with_pat, "repo"])
            except subprocess.CalledProcessError:
                raise RuntimeError(
                    f"Unable to clone {repo_url} via {GITHUB_PROXY_DOMAIN}"
                )

            logger.debug(f"Checked out {repo_url} to repo/")
            os.chdir("repo")

            checked_out = run_cmd(["git", "checkout", branch], raise_exc=False)
            if checked_out != 0:
                run_cmd(["git", "checkout", "-b", branch])

            extraction_dir = Path("downloads")
            extraction_dir.mkdir(parents=True, exist_ok=True)
            extraction_path = str(
                (extraction_dir / f"extracted-stats-{timestamp}.sqlite").resolve()
            )
            try:
                os.chdir(job_runner_dir)
                run_cmd(
                    [
                        "bash",
                        "scripts/run.sh",
                        "-m",
                        "jobrunner.extract_stats",
                        "--since",
                        since_timestamp,
                        extraction_path,
                    ]
                )
                os.chdir(f"{d}/repo")
            except subprocess.CalledProcessError:
                os.chdir(current_dir)
                raise RuntimeError("Unable to run extraction")

            run_cmd(["git", "add", "--all"])

            commit_returncode = run_cmd(
                ["git", "commit", "-m", f"{commit_message}"],
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
                        branch,
                    ]
                )
                print("Pushed new extraction file")
                extracted = True
            else:
                print("Nothing to do!")
        finally:
            # ensure we do not maintain an open handle on the temp dir, or else
            # the clean up fails
            os.chdir(current_dir)

        return extracted


def extract(options, current_dir):
    try:
        _, cfg = config.load_config(options, current_dir, entrypoint="jobrunner_stats")
        main(
            current_dir,
            options.job_runner_dir,
            options.days,
            options.repo_url,
            options.branch,
            cfg["private_token"],
        )

    except Exception as exc:
        if options.verbose > 0:
            raise
        sys.exit(exc)


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", "-v", action="count", default=0)
    parser.add_argument("--days", type=int, default=7, help="Days to extract")
    parser.add_argument("--job-runner-dir", default="/e/job-runner")
    parser.add_argument(
        "--repo_url", default="https://github.com/opensafely-core/job-runner-stats.git"
    )
    parser.add_argument("--branch", default="main")
    options = parser.parse_args()
    extract(options, Path(os.getcwd()))


if __name__ == "__main__":
    run()
