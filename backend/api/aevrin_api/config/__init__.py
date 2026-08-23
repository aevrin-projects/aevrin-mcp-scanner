"""Runtime configuration. Every environment variable the app reads is declared
in one Settings model here, so a missing variable fails at import with a name
instead of at request time with an AttributeError.
"""

from aevrin_api.config.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]
