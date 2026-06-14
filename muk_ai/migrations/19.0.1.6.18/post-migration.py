def migrate(cr, version):
    cr.execute(
        """
        UPDATE muk_ai_model
        SET context_window = 1000000
        WHERE technical_name = 'claude-opus-4-6'
        AND context_window = 200000
        """
    )
    cr.execute(
        """
        UPDATE muk_ai_model
        SET active = false
        WHERE technical_name = 'claude-haiku-3-5'
        AND active = true
        """
    )
    cr.execute(
        """
        UPDATE muk_ai_provider
        SET default_model_id = (
            SELECT res_id FROM ir_model_data
            WHERE module = 'muk_ai' AND name = 'model_gemini_3_5_flash'
        )
        WHERE id = (
            SELECT res_id FROM ir_model_data
            WHERE module = 'muk_ai' AND name = 'provider_google'
        )
        AND default_model_id = (
            SELECT res_id FROM ir_model_data
            WHERE module = 'muk_ai' AND name = 'model_gemini_3_flash_preview'
        )
        """
    )
