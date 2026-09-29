"""Database access. Owns the Supabase REST client; nothing here knows a
product rule, and nothing above it constructs a client of its own.
"""

from aevrin_api.db.supabase import MAX_ROWS, SupabaseRest, SupabaseRestError, select_all

__all__ = ["MAX_ROWS", "SupabaseRest", "SupabaseRestError", "select_all"]
