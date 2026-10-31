// @odoo-module

import { patch } from '@web/core/utils/patch';

import { MukAISystray } from '@muk_ai/webclient/systray/systray';

import { getRecentSkillNames, recordSkillUse } from '@muk_ai_skills/chat/recent_skills';
import { requestSkillsPanel } from '@muk_ai_skills/chat/skill_cache';

/** Offer the skills of the record on screen as the actions of the AI menu. */
patch(MukAISystray.prototype, 'muk_ai_skills.MukAISystray', {
    async loadActions() {
        const loadDefault = this._super.bind(this);
        const { record } = this.state;
        const skills = record
            ? await this.orm.call('muk_ai.skill', 'fetch_skills', ['chat', record])
            : [];
        const own = skills.filter((skill) => skill.models.length);
        if (!own.length) {
            return loadDefault();
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
            return this._super(...arguments);
        }
        const id = await this.createSession();
        requestSkillsPanel(id);
        this.chatWindow.open(id);
    },
    async runAction(sessionId, action) {
        if (!action.skill) {
            return this._super(...arguments);
        }
        const snapshot = await this.orm.call(
            'muk_ai.session',
            'invoke_skill_from_chat',
            [sessionId, action.skill],
            { user_input: false },
        );
        recordSkillUse(action.skill);
        return snapshot;
    },
});
