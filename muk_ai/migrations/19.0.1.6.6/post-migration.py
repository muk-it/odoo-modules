def migrate(cr, version):
    cr.execute(
        """
        UPDATE ir_act_server
        SET state = 'ai_session'
        WHERE state = 'code'
          AND id IN (
              SELECT c.ir_actions_server_id
              FROM ir_cron c
              JOIN ir_model_data d ON d.res_id = c.id
              WHERE d.module = 'muk_ai'
                AND d.model = 'ir.cron'
                AND d.name IN (
                    'cron_run_pending_sessions_1',
                    'cron_run_pending_sessions_2',
                    'cron_run_pending_sessions_3',
                    'cron_run_pending_sessions_4'
                )
          )
        """
    )
