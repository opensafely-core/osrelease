# This file is currently maintained in the release-hatch project, until we can
# extract it into it's own library.
#
# https://github.com/opensafely-core/release-hatch
#
# Until then, do not make local changes, rather copy the latest version of this
# file into your project.
from datetime import datetime
from typing import Dict, List

from pydantic import BaseModel


class UrlFileName(str):
    """str file name that normalises path separators."""

    @classmethod
    def __get_validators__(cls):
        """Tell pydantic how to validate me."""
        yield cls.validate

    @classmethod
    def validate(cls, value):
        return str(value).replace("\\", "/")


class FileSchema(BaseModel):
    """Metadata for a workspace file."""

    name: UrlFileName
    url: UrlFileName
    size: int
    sha256: str
    user: str = None
    date: datetime = None


class IndexSchema(BaseModel):
    """An index of files in a workspace.

    This must match the json format that the SPA's client API expects.
    """

    files: List[FileSchema]


class Release(BaseModel):
    """Request a release.

    Files is a dict with {name: sha256} mapping.
    """

    files: Dict[UrlFileName, str]


class ReleaseFile(BaseModel):
    """File to upload to job-server.

    This schema is unique to the release-hatch API, as the client just
    indicates which file release-hatch should upload, rather than uploading the
    bytes itself.
    """

    name: str
