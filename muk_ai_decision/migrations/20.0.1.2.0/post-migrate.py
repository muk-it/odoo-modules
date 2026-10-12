from __future__ import annotations

from odoo import SUPERUSER_ID, Command, api
from odoo.sql_db import Cursor


def migrate_gates(cr: Cursor) -> None:
    """Turn each agent action with a gate into a decision that runs a copy of it.

    The copy runs for the records answered yes and the unsure ones, as the gate did.
    """
    cr.execute("""
        SELECT id, agent_gate->>'en_US', agent_gate_min_confidence
          FROM ir_act_server
         WHERE state = 'ai_agent'
           AND agent_gate->>'en_US' <> ''
    """)
    rows = cr.fetchall()
    env = api.Environment(cr, SUPERUSER_ID, {})
    for action_id, gate, confidence in rows:
        action = env['ir.actions.server'].browse(action_id)
        agent = action.copy(
            {
                'name': action.name,
                'base_automation_id': False,
                'binding_model_id': False,
                'usage': 'ir_actions_server',
            }
        )
        action.write(
            {
                'state': 'ai_decision',
                'decision_question_ids': [
                    Command.create(
                        {
                            'kind': 'noul',
                            'name': gate,
                            'min_confidence': confidence or 0.8,
                            'route_answer': 'yes',
                            'route_action_id': agent.id,
                            'unsure_action_id': agent.id,
                        }
                    )
                ],
            }
        )


def migrate_options(cr: Cursor) -> None:
    """Turn the typed options of each question into option records.

    A route on one of the options moves onto that option.
    """
    cr.execute("""
        SELECT id, options, route_answer, route_action_id
          FROM muk_ai_decision_question
         WHERE options IS NOT NULL
           AND field_id IS NULL
    """)
    env = api.Environment(cr, SUPERUSER_ID, {})
    for question_id, text, answer, action_id in cr.fetchall():
        values = []
        for sequence, line in enumerate(text.splitlines()):
            label, _sep, description = line.partition(':')
            if label.strip():
                routed = bool(action_id) and (answer or '').strip().casefold() == (
                    label.strip().casefold()
                )
                values.append(
                    {
                        'question_id': question_id,
                        'sequence': sequence,
                        'name': label.strip(),
                        'description': description.strip() or False,
                        'action_id': action_id if routed else False,
                    }
                )
        env['muk_ai.decision.option'].create(values)
        if any(value['action_id'] for value in values):
            cr.execute(
                """
                UPDATE muk_ai_decision_question
                   SET route_answer = NULL, route_action_id = NULL
                 WHERE id = %s
                """,
                [question_id],
            )


def migrate(cr: Cursor, version: str | None) -> None:
    """Carry the 1.1.0 settings over to goals, options, messages and decision steps.

    Shadow actions only logged, so the rules and schedules running them stop.
    """
    cr.execute("""
        UPDATE muk_ai_decision_question
           SET kind = 'field', field_scale = kind = 'score'
         WHERE field_id IS NOT NULL
    """)
    cr.execute("""
        UPDATE muk_ai_provider AS provider
           SET api_region = CASE data.name
                   WHEN 'provider_typesafe' THEN 'default' ELSE 'custom' END,
               api_url = NULL,
               active = TRUE
          FROM ir_model_data AS data
         WHERE data.module = 'muk_ai_decision'
           AND data.name IN ('provider_typesafe', 'provider_decis')
           AND data.res_id = provider.id
           AND NOT provider.active
           AND provider.api_key IS NULL
           AND provider.api_url IN ('https://api.typesafe.ai', 'http://localhost:8000')
    """)
    cr.execute("""
        UPDATE ir_act_server
           SET decision_message_count = 1
         WHERE decision_include_message
    """)
    cr.execute("""
        UPDATE muk_ai_decision_question AS question
           SET unsure_action_id = action.decision_unsure_action_id
          FROM ir_act_server AS action
         WHERE action.id = question.action_id
           AND action.decision_unsure_action_id IS NOT NULL
    """)
    cr.execute("""
        UPDATE base_automation
           SET active = FALSE
         WHERE id IN (
            SELECT base_automation_id FROM ir_act_server WHERE decision_shadow
        )
    """)
    cr.execute("""
        UPDATE ir_cron
           SET active = FALSE
         WHERE ir_actions_server_id IN (
            SELECT id FROM ir_act_server WHERE decision_shadow
        )
    """)
    migrate_options(cr)
    migrate_gates(cr)
