// @odoo-module

import { useEffect } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { useService } from '@web/core/utils/hooks';

import { patchChatSurfaces } from '@muk_ai/chat/surfaces';
import { formatError } from '@muk_ai/chat/utils';
import { allSlashCommands } from '@muk_ai/chat/session/use_ai_session';

import { recordSkillUse } from '@muk_ai_skills/chat/recent_skills';
import { findSkill, setSkills } from '@muk_ai_skills/chat/skill_cache';

/**
 * Resolve the skill a slash command head routes to, or null when a command of
 * the same name exists. Commands always take precedence so a skill named like
 * `help` or `remember` cannot hijack one. Read on every call, because an addon
 * registers its commands as it loads.
 * @param {number} sessionId the session whose skills to search
 * @param {string} head the slash command head, without the leading slash
 * @returns {object|null} the matching skill, or null when a command wins
 */
export function resolveChatSkill(sessionId, head) {
    const name = (head || '').toLowerCase();
    if (allSlashCommands().some((c) => c.name.slice(1).toLowerCase() === name)) {
        return null;
    }
    return findSkill(sessionId, name);
}

/**
 * Wrap a chat component's send handler to dispatch `/skill` slash commands
 * server-side, and keep the per-session skill cache in sync with the session id.
 * The shared runner is exposed as ``component.runSkill`` so the composer's
 * skills panel invokes a skill through the very same path.
 * @param {object} component the chat component whose session is patched
 */
function installSkillRouting(component) {
    const orm = useService('orm');
    const session = component.session;
    component.runSkill = async (name, userInput) => {
        try {
            const snapshot = await orm.call(
                'muk_ai.session',
                'invoke_skill_from_chat',
                [session.state.sessionId, name],
                { user_input: userInput || false },
            );
            recordSkillUse(name);
            session.applySnapshot(snapshot);
        } catch (error) {
            component.env.services.notification.add(
                _t('Failed to invoke skill: %s', formatError(error)),
                { type: 'danger' },
            );
        }
        session.state.focusToken += 1;
    };
    const originalOnSend = session.onSend.bind(session);
    session.onSend = async () => {
        const trimmed = (session.state.input || '').trim();
        if (trimmed.startsWith('/')) {
            const match = trimmed.match(/^\/(\S+)\s*(.*)$/);
            const head = (match?.[1] || '').toLowerCase();
            const rest = (match?.[2] || '').trim();
            const skill = resolveChatSkill(session.state.sessionId, head);
            if (skill) {
                session.state.input = '';
                await component.runSkill(skill.name, rest);
                return;
            }
        }
        return originalOnSend();
    };
    useEffect(
        (sessionId) => {
            if (!sessionId) {
                return;
            }
            let cancelled = false;
            (async () => {
                try {
                    const skills = await orm.call(
                        'muk_ai.session',
                        'available_skill_names',
                        [],
                        { session_id: sessionId },
                    );
                    if (!cancelled) {
                        setSkills(sessionId, skills || []);
                    }
                } catch {
                    if (!cancelled) {
                        setSkills(sessionId, []);
                    }
                }
            })();
            return () => {
                cancelled = true;
            };
        },
        () => [component.session.state.sessionId],
    );
}

patchChatSurfaces(() => ({
    setup() {
        super.setup();
        installSkillRouting(this);
    },
}));
