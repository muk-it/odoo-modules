import { useEffect } from '@odoo/owl';

import { patch } from '@web/core/utils/patch';
import { _t } from '@web/core/l10n/translation';
import { useService } from '@web/core/utils/hooks';

import { AIChat } from '@muk_ai/chat/chat';
import { ChatWindow } from '@muk_ai/chat/window/chat_window';
import { formatError } from '@muk_ai/chat/utils';

import {
    clearSkills,
    findSkill,
    setActiveSessionId,
    setSkills,
} from '@muk_ai_skills/chat/skill_cache';

/**
 * Wrap a chat component's send handler to dispatch `/skill` slash commands
 * server-side, and keep the per-session skill cache in sync with the session id.
 * @param {object} component the chat component whose session is patched
 */
function installSkillRouting(component) {
    const orm = useService('orm');
    const session = component.session;
    const originalOnSend = session.onSend.bind(session);
    session.onSend = async () => {
        const trimmed = (session.state.input || '').trim();
        if (trimmed.startsWith('/')) {
            const match = trimmed.match(/^\/(\S+)\s*(.*)$/);
            const head = (match?.[1] || '').toLowerCase();
            const rest = (match?.[2] || '').trim();
            const skill = findSkill(session.state.sessionId, head);
            if (skill) {
                session.state.input = '';
                try {
                    const snapshot = await orm.call(
                        'muk_ai.session',
                        'invoke_skill_from_chat',
                        [session.state.sessionId, skill.name],
                        { user_input: rest || false },
                    );
                    session.applySnapshot(snapshot);
                } catch (error) {
                    component.env.services.notification.add(
                        _t('Failed to invoke skill: %s', formatError(error)),
                        { type: 'danger' },
                    );
                }
                session.state.focusToken += 1;
                return;
            }
        }
        return originalOnSend();
    };
    useEffect(
        (sessionId) => {
            if (!sessionId) {
                setActiveSessionId(null);
                return () => setActiveSessionId(null);
            }
            setActiveSessionId(sessionId);
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
                clearSkills(sessionId);
                setActiveSessionId(null);
            };
        },
        () => [component.session.state.sessionId],
    );
}

/** Install skill slash-command routing on the main AI chat. */
patch(AIChat.prototype, {
    setup() {
        super.setup();
        installSkillRouting(this);
    },
});

/** Install skill slash-command routing on the chat window. */
patch(ChatWindow.prototype, {
    setup() {
        super.setup();
        installSkillRouting(this);
    },
});
