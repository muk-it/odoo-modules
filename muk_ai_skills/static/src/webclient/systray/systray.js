import { _t } from '@web/core/l10n/translation';
import { patch } from '@web/core/utils/patch';

import { formatError } from '@muk_ai/chat/utils';
import { MukAISystray } from '@muk_ai/webclient/systray/systray';

import { getRecentSkillNames, recordSkillUse } from '@muk_ai_skills/chat/recent_skills';
import { openSkillsPanel } from '@muk_ai_skills/chat/skill_cache';

patch(MukAISystray.prototype, {
    async loadActions() {
        const { record } = this.state;
        const skills = record
            ? await this.orm
                  .call('muk_ai.skill', 'fetch_skills', ['chat', record])
                  .catch(() => [])
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
        this.menu.close();
        const id = await this.createSession();
        openSkillsPanel.add(id);
        this.chatWindow.open(id);
    },
    async runAction(sessionId, action) {
        if (!action.skill) {
            return super.runAction(sessionId, action);
        }
        try {
            await this.orm.call('muk_ai.session', 'invoke_skill_from_chat', [
                sessionId,
                action.skill,
            ]);
            recordSkillUse(action.skill);
        } catch (error) {
            this.notification.add(
                _t('Failed to invoke skill: %s', formatError(error)),
                {
                    type: 'danger',
                },
            );
        }
    },
});
