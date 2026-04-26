def migrate(cr, version):
    cr.execute("ALTER TABLE muk_ai_session DROP COLUMN IF EXISTS tool_log")
