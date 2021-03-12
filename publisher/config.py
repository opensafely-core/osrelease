import os
from pathlib import Path


def get_config_file(env, filename="osrelease_config.py"):
    """Lookup possible config.py file locations.

    We do this so we can centrally configure an osrelease installation w/o
    needing users to have specific environment variables set.
    """
    lookup = [
        # current dir
        Path(os.getcwd()),
        # virtualenv directory
        Path(env.get("VIRTUAL_ENV", "doesnotexist.osrelease")),
        # moduel directory
        Path(__file__).parent,
    ]

    for path in lookup:
        config = path / filename
        if config.exists():
            return config


def get_config(env=os.environ):
    config = {}
    config_file = get_config_file(env)
    if config_file:
        exec(config_file.read_text(), {}, config)
    return config


def get_private_github_token(env=os.environ):
    config = get_config(env)
    return config.get("PRIVATE_REPO_ACCESS_TOKEN", "").strip()
