def migrate(cr, version):
    cr.execute("""
        ALTER TABLE muk_mcp_key
        ADD COLUMN IF NOT EXISTS scope VARCHAR DEFAULT 'write'
    """)
