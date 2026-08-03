import { useExternalListener, useRef, useState } from '@odoo/owl';

import { hasTouch } from '@web/core/browser/feature_detection';
import { patch } from '@web/core/utils/patch';

import { ChatComposer } from '@muk_ai/chat/composer/chat_composer';

import { skillStore } from '@muk_ai_skills/chat/skill_cache';
import { SkillsPanel } from '@muk_ai_skills/chat/skills_panel';

ChatComposer.components = { ...ChatComposer.components, SkillsPanel };
ChatComposer.props = {
    ...ChatComposer.props,
    sessionId: { type: [Number, String], optional: true },
    onInvokeSkill: { type: Function, optional: true },
};

/** Merge visible skills into the slash suggestions and the skills panel. */
patch(ChatComposer.prototype, {
    setup() {
        super.setup();
        this.hostRef = useRef('composerHost');
        this.skillState = useState(skillStore);
        this.localState.skillsOpen = false;
        useExternalListener(document, 'mousedown', (event) => {
            if (
                this.localState.skillsOpen &&
                !this.hostRef.el?.contains(event.target)
            ) {
                this.localState.skillsOpen = false;
            }
        });
    },
    /** Close the panel as soon as the composer starts a slash command. */
    onInputChange(event) {
        if (event.target.value.trimStart().startsWith('/')) {
            this.localState.skillsOpen = false;
        }
        return super.onInputChange(event);
    },
    get slashCommands() {
        const builtIn = super.slashCommands;
        const value = (this.props.value || '').trim();
        if (!value.startsWith('/')) {
            return builtIn;
        }
        const prefix = value.split(/\s+/)[0].toLowerCase();
        const skillEntries = this.sessionSkills.map((skill) => ({
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
    /** Return the session skills through the reactive store, so fills re-render. */
    get sessionSkills() {
        return (this.props.sessionId && this.skillState[this.props.sessionId]) || [];
    },
    get hasSkills() {
        return this.sessionSkills.length > 0;
    },
    get showSkillsPanel() {
        return this.localState.skillsOpen && !this.props.disabled;
    },
    /** Focus the panel search only where a keyboard will not cover the list. */
    get skillsAutofocus() {
        return !hasTouch();
    },
    /** Toggle the panel, dropping the composer caret so no keyboard covers it. */
    toggleSkillsPanel() {
        if (!this.localState.skillsOpen && this.showSlashMenu) {
            return;
        }
        this.localState.skillsOpen = !this.localState.skillsOpen;
        if (this.localState.skillsOpen) {
            this.inputRef.el?.blur();
        }
    },
    closeSkillsPanel() {
        this.localState.skillsOpen = false;
        this.inputRef.el?.focus();
    },
    invokeSkill(name) {
        this.localState.skillsOpen = false;
        this.props.onInvokeSkill?.(name);
    },
});
