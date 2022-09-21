import logging

import pytest

from publisher import release


def test_redacting_logger(capsys):

    logger = logging.getLogger(__name__ + ".test_redacting_logger")
    logger.setLevel(logging.DEBUG)
    ch = release.RedactingStreamHandler("token")
    ch.setLevel(logging.DEBUG)
    logger.addHandler(ch)
    logger.info("https://token@github-proxy.opensafely.org")
    logger.info("https://user:token@github-proxy.opensafely.org")

    _, err = capsys.readouterr()

    assert (
        err
        == "https://xxxxxx@github-proxy.opensafely.org\nhttps://user:xxxxxx@github-proxy.opensafely.org\n"
    )


def test_releaseno_args(tmp_path):
    options = release.parser.parse_args([])
    with pytest.raises(SystemExit) as ctx:
        release.release(options, tmp_path)

    assert "Could not find metadata/manifest.json" in str(ctx.value)


def test_get_authenticated_repo_url_success():
    repo = release.get_authenticated_repo_url(
        "https://github.com/org/repo", "TOKEN", "USER", "BACKEND"
    )
    assert (
        repo
        == "https://osrelease-BACKEND-USER:TOKEN@github-proxy.opensafely.org/org/repo"
    )


def test_get_authenticated_repo_url_not_github():
    repo = "https://evil.com/org/repo"
    new = release.get_authenticated_repo_url(repo, "TOKEN", "USER", "BACKEND")
    assert repo == new


def test_get_authenticated_repo_url_existing_creds():
    with pytest.raises(AssertionError):
        release.get_authenticated_repo_url(
            "https://user@github.com/org/repo", "TOKEN", "USER", "BACKEND"
        )
    with pytest.raises(AssertionError):
        release.get_authenticated_repo_url(
            "https://user:pass@github.com/org/repo", "TOKEN", "USER", "BACKEND"
        )
