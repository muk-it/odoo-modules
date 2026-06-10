def migrate(cr, version):
    cr.execute("DROP TABLE IF EXISTS muk_ai_session_ir_attachment_rel")
