import { browser } from '@web/core/browser/browser';
import { _t } from '@web/core/l10n/translation';
import { user } from '@web/core/user';
import { patch } from '@web/core/utils/patch';

import { ChatComposer } from '@muk_ai/chat/composer/composer';
import { ChatConversation } from '@muk_ai/chat/conversation/conversation';
import { sessionSendRoutes, slashCommands } from '@muk_ai/core/session/session';
import { describeToolBlock, toolBlockDecorators } from '@muk_ai/core/session/turns';
import { MukAISystray } from '@muk_ai/webclient/systray/systray';

const RECENT_LIMIT = 3;

/**
 * Tell whether what the session has open satisfies a skill's scope, as
 * `muk_ai.skill._scope_satisfied_by` does. A chatter skill counts as a record
 * skill here; the server refuses it on a model without a chatter.
 * @param {object} skill a skill descriptor of the snapshot
 * @param {object|null} viewContext the session's pinned view context
 * @returns {boolean} true when the skill can run right now
 */
export function skillScopeSatisfied(skill, viewContext) {
    const context = viewContext || {};
    const model = context.model || '';
    if (skill.scope !== 'any') {
        if (!model || (skill.scope !== 'context' && context.kind !== 'record')) {
            return false;
        }
    }
    return !skill.models.length || skill.models.includes(model);
}

/**
 * Return the technical names of the skills the user invoked last, newest first.
 * @returns {string[]} the names, empty when the storage cannot be read
 */
export function recentSkillNames() {
    try {
        const names = JSON.parse(
            browser.localStorage.getItem(`muk_ai_skills.recent.${user.userId}`),
        );
        return Array.isArray(names) ? names : [];
    } catch {
        return [];
    }
}

/**
 * Run a skill in a chat and remember it as recently used.
 * @param {object} session the chat
 * @param {string} name the technical name of the skill
 * @param {string} [userInput] free text sent along with it
 */
export async function invokeSkill(session, name, userInput = '') {
    const snapshot = await session.run(
        'invoke_skill_from_chat',
        [name],
        _t('Failed to invoke skill'),
        { user_input: userInput || false },
    );
    if (snapshot) {
        const names = [name, ...recentSkillNames().filter((n) => n !== name)];
        browser.localStorage.setItem(
            `muk_ai_skills.recent.${user.userId}`,
            JSON.stringify(names.slice(0, RECENT_LIMIT)),
        );
    }
}

sessionSendRoutes.add('muk_ai_skills', async (session, text) => {
    const [word, ...rest] = text.trim().split(/\s+/);
    const name = word.toLowerCase();
    const skill =
        name.startsWith('/') &&
        !slashCommands.contains(name) &&
        (session.data.skills || []).find((s) => `/${s.name}` === name);
    if (!skill) {
        return false;
    }
    session.state.input = '';
    await invokeSkill(session, skill.name, rest.join(' '));
    return true;
});

patch(ChatComposer.prototype, {
    get items() {
        const items = super.items;
        const prefix = this.props.session.state.input.trim().split(/\s+/)[0];
        if (this.agentMode || !prefix.startsWith('/')) {
            return items;
        }
        const { skills = [], view_context } = this.props.session.data;
        const names = new Set(items.map((item) => item.name));
        const offered = skills
            .filter(
                (skill) =>
                    `/${skill.name}`.startsWith(prefix.toLowerCase()) &&
                    !names.has(`/${skill.name}`) &&
                    skillScopeSatisfied(skill, view_context),
            )
            .map((skill) => ({
                key: `/${skill.name}`,
                name: `/${skill.name}`,
                hint: skill.description || skill.label,
                command: {},
            }));
        return [...items, ...offered];
    },
});

patch(ChatConversation.prototype, {
    get suggestions() {
        const { skills = [], view_context } = this.props.session.data;
        const own = skills
            .filter(
                (skill) =>
                    skill.models.length && skillScopeSatisfied(skill, view_context),
            )
            .map((skill) => ({
                label: skill.label,
                preview: skill.description,
                skill: skill.name,
            }));
        return own.length ? own : super.suggestions;
    },
    onSuggestion(suggestion) {
        if (suggestion.skill) {
            return invokeSkill(this.props.session, suggestion.skill);
        }
        return super.onSuggestion(suggestion);
    },
});

patch(MukAISystray.prototype, {
    async loadActions() {
        const { record } = this.state;
        const skills = record
            ? await this.chat.orm.call('muk_ai.skill', 'fetch_skills', ['chat', record])
            : [];
        const own = skills.filter((skill) => skill.models.length);
        if (!own.length) {
            return super.loadActions();
        }
        const recent = recentSkillNames();
        const rank = (skill) =>
            recent.includes(skill.name) ? recent.indexOf(skill.name) : recent.length;
        return own
            .sort((a, b) => rank(a) - rank(b))
            .map((skill) => ({
                label: skill.label,
                preview: skill.description,
                skill: skill.name,
            }));
    },
    async more() {
        if (!this.state.actions.some((action) => action.skill)) {
            return super.more();
        }
        const id = await this.chat.createSession();
        this.chat.session(id).state.skillsOpen = true;
        this.chat.openWindow(id);
    },
    runAction(session, action) {
        return action.skill
            ? invokeSkill(session, action.skill)
            : super.runAction(session, action);
    },
});

toolBlockDecorators.add('muk_ai_skills.invoke_skill', (block) => {
    if (block.name === 'invoke_skill') {
        describeToolBlock(block, {
            icon: () => 'flash_on',
            label: ({ args, result }) =>
                _t('Use the skill %s', result?.label || args.skill_name || ''),
            band: ({ result }) =>
                (result?.resources || []).map((resource) => resource.name).join(', '),
        });
    }
});
