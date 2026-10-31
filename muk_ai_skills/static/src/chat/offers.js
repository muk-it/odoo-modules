import { useState } from '@odoo/owl';

import { patch } from '@web/core/utils/patch';

import { AIChat } from '@muk_ai/chat/chat';
import { MukAISystray } from '@muk_ai/webclient/systray/systray';

import { getRecentSkillNames, recordSkillUse } from '@muk_ai_skills/chat/recent_skills';
import { skillScopeSatisfied } from '@muk_ai_skills/chat/scope';
import { skillStore, skillsOpening } from '@muk_ai_skills/chat/skill_cache';

/**
 * Offer skills the way a suggestion is offered.
 * @param {Array} skills skill descriptors
 * @returns {Array} `{label, preview, skill}` entries
 */
function skillOffers(skills) {
    return skills.map((skill) => ({
        label: skill.label,
        preview: skill.description,
        skill: skill.name,
    }));
}

patch(AIChat.prototype, {
    setup() {
        super.setup();
        this.skillState = useState(skillStore);
    },
    get sessionSuggestions() {
        const { sessionId, viewContext } = this.session.state;
        const own = (this.skillState[sessionId] || []).filter(
            (skill) => skill.models.length && skillScopeSatisfied(skill, viewContext),
        );
        return own.length ? skillOffers(own) : super.sessionSuggestions;
    },
    onSubmitSuggestion(suggestion) {
        if (suggestion.skill) {
            return this.runSkill(suggestion.skill);
        }
        return super.onSubmitSuggestion(suggestion);
    },
});

patch(MukAISystray.prototype, {
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
        return skillOffers(own.sort((a, b) => rank(a) - rank(b)));
    },
    async more() {
        if (!this.state.actions.some((action) => action.skill)) {
            return super.more();
        }
        this.menu.close();
        const id = await this.createSession();
        skillsOpening.add(id);
        this.chatWindow.open(id);
    },
    async runAction(sessionId, action) {
        if (!action.skill) {
            return super.runAction(sessionId, action);
        }
        await this.orm.call('muk_ai.session', 'invoke_skill_from_chat', [
            sessionId,
            action.skill,
        ]);
        recordSkillUse(action.skill);
    },
});
