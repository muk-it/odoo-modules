import { patch } from '@web/core/utils/patch';

import { ChatComposer } from '@muk_ai/chat/composer/chat_composer';

import { getSkills } from '@muk_ai_skills/chat/skill_cache';

ChatComposer.props = {
    ...ChatComposer.props,
    sessionId: { type: [Number, String], optional: true },
};

/** Merge visible skills into the composer's slash-command suggestions. */
patch(ChatComposer.prototype, {
    get slashCommands() {
        const builtIn = super.slashCommands;
        const value = (this.props.value || '').trim();
        if (!value.startsWith('/')) {
            return builtIn;
        }
        const prefix = value.split(/\s+/)[0].toLowerCase();
        const skillEntries = getSkills(this.props.sessionId).map((skill) => ({
            name: `/${skill.name}`,
            hint: skill.description
                ? `Skill: ${skill.description}`
                : `Invoke skill ${skill.label || skill.name}`,
            isSkill: true,
        }));
        const matchingSkills = skillEntries.filter((c) => c.name.startsWith(prefix));
        const seen = new Set(builtIn.map((c) => c.name));
        const merged = [...builtIn];
        for (const entry of matchingSkills) {
            if (!seen.has(entry.name)) {
                merged.push(entry);
                seen.add(entry.name);
            }
        }
        return merged;
    },
});
