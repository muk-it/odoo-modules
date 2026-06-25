def migrate(cr, version):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'muk_mcp_prompt' AND column_name = 'code'
    """)
    has_code = cr.fetchone()
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'muk_mcp_prompt' AND column_name = 'body'
    """)
    has_body = cr.fetchone()
    if has_code and not has_body:
        cr.execute('ALTER TABLE muk_mcp_prompt RENAME COLUMN code TO body')
