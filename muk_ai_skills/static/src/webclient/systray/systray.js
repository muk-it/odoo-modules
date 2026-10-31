// @odoo-module

import { patch } from '@web/core/utils/patch';

import { MukAISystray } from '@muk_ai/webclient/systray/systray';

import { getRecentSkillNames, recordSkillUse } from '@muk_ai_skills/chat/recent_skills';
import { skillsOpening } from '@muk_ai_skills/chat/skill_cache';

patch(MukAISystray.prototype, {
    /**
     * Offer the skills of the record on screen, recently used first, else
     * the default agent's suggestions.
     * @returns {Promise<Array>} `{label, preview, skill}` entries
     */
    async loadActions() {
        const { record } = this.state;
        const skills = record
            ? await this.orm.call('muk_ai.skill', 'fetch_skills', ['chat', record])
            : [];
        const own = skills.filter((skill) => skill.models.length);
        if (!own.length) {
            return super.loadActions();
        }
        const recent = getRecentSkillNames();
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
        const id = await this._createSession();
        skillsOpening.add(id);
        this.chatWindow.open(id);
    },
    async runAction(sessionId, action) {
        if (!action.skill) {
            return super.runAction(sessionId, action);
        }
        const snapshot = await this.orm.call(
            'muk_ai.session',
            'invoke_skill_from_chat',
            [[sessionId], action.skill],
        );
        recordSkillUse(action.skill);
        return snapshot;
    },
});
