import os
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
        # virtualenv directory
        Path(env.get("VIRTUAL_ENV", "doesnotexist.osrelease")) / filename,
        # module directory
        Path(__file__).parent / filename,
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


def get_config_value(name, env=os.environ):
    config = get_config(env)
    if name in config:
        return config[name]
    return None
