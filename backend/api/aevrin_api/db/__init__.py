"""Database access. Owns the Supabase REST client; nothing here knows a
product rule, and nothing above it constructs a client of its own.
"""

from aevrin_api.db.supabase import SupabaseRest, SupabaseRestError

__all__ = ["SupabaseRest", "SupabaseRestError"]
