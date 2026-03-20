"""SMUS CI/CD CLI package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("aws-smus-cicd-cli")
except PackageNotFoundError:
    __version__ = "unknown"
