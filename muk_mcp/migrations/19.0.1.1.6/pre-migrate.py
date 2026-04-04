def migrate(cr, version):
    cr.execute("""
        ALTER TABLE muk_mcp_log
        ADD COLUMN IF NOT EXISTS res_id INTEGER,
        ADD COLUMN IF NOT EXISTS res_ids JSONB,
        ADD COLUMN IF NOT EXISTS request_data TEXT,
        ADD COLUMN IF NOT EXISTS response_data TEXT,
        ADD COLUMN IF NOT EXISTS ip_address VARCHAR
    """)
