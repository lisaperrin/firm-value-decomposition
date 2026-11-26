"""Exceptions raised by the package.

Everything user-facing derives from :class:`FirmValueError`, so the command
line can exit with one readable line and the MCP server can forward the
message as a tool error.
"""

from __future__ import annotations


class FirmValueError(Exception):
    """Base class for errors the package reports to users."""


class PanelError(FirmValueError):
    """The firm-year panel violates the schema."""


class ParametersError(FirmValueError):
    """A parameters file or mapping cannot be turned into :class:`Parameters`."""


class InputFileError(FirmValueError):
    """A file the command needs is missing or unreadable."""
