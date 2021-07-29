import os

from setuptools import find_packages, setup

with open(os.path.join("publisher", "VERSION")) as f:
    version = f.read().strip()

setup(
    name="opensafely-output-publisher",
    version=version,
    packages=find_packages(),
    url="https://github.com/opensafely/output-publisher",
    author="OpenSAFELY",
    author_email="tech@opensafely.org",
    python_requires=">=3.7",
    install_requires=[],
    entry_points={
        "console_scripts": [
            "osrelease=publisher.release:run",
            "jobrunnerstats=publisher.jobrunner_stats:run",
        ]
    },
    include_package_data=True,
    classifiers=["License :: OSI Approved :: GNU General Public License v3 (GPLv3)"],
)
