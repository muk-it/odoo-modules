import { Component, useEffect, useRef, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';

import { getRecentSkillNames } from '@muk_ai_skills/chat/recent_skills';

/** Browsable list of the session skills, grouped into recent and all. */
export class SkillsPanel extends Component {
    static template = 'muk_ai_skills.SkillsPanel';
    static props = {
        skills: { type: Array },
        autofocus: { type: Boolean, optional: true },
        onSelect: { type: Function },
        onClose: { type: Function },
    };
    static defaultProps = { autofocus: false };
    setup() {
        this.rootRef = useRef('root');
        this.searchRef = useRef('search');
        this.state = useState({ filter: '', activeIndex: 0 });
        useEffect(
            () => {
                const target = this.props.autofocus ? this.searchRef : this.rootRef;
                target.el?.focus();
            },
            () => [],
        );
        useEffect(
            () => {
                this.state.activeIndex = 0;
            },
            () => [this.entries.length],
        );
    }
    /** Return the matching skills, recently used first, tagged with their group. */
    get entries() {
        const filter = this.state.filter.trim().toLowerCase();
        const recent = getRecentSkillNames();
        const used = recent
            .map((name) => this.props.skills.find((skill) => skill.name === name))
            .filter(Boolean);
        const ordered = [
            ...used,
            ...this.props.skills.filter((skill) => !used.includes(skill)),
        ];
        const recentNames = new Set(recent);
        let previous = null;
        return ordered
            .filter((skill) =>
                filter
                    ? `${skill.label || ''} ${skill.name} ${skill.description || ''}`
                          .toLowerCase()
                          .includes(filter)
                    : true,
            )
            .map((skill) => {
                const group = recentNames.has(skill.name)
                    ? _t('Recently used')
                    : _t('All skills');
                const first = group !== previous;
                previous = group;
                return { skill, group, first };
            });
    }
    onFilterInput(event) {
        this.state.filter = event.target.value;
    }
    hoverSkill(index) {
        this.state.activeIndex = index;
    }
    pickSkill(index) {
        const entry = this.entries[index];
        if (entry) {
            this.props.onSelect(entry.skill.name);
        }
    }
    onKeydown(event) {
        const count = this.entries.length;
        if (event.key === 'Escape') {
            event.preventDefault();
            this.props.onClose();
            return;
        }
        if (!count) {
            return;
        }
        if (event.key === 'ArrowDown') {
            event.preventDefault();
            this.state.activeIndex = (this.state.activeIndex + 1) % count;
        } else if (event.key === 'ArrowUp') {
            event.preventDefault();
            this.state.activeIndex = (this.state.activeIndex - 1 + count) % count;
        } else if (event.key === 'Enter' && !event.isComposing) {
            event.preventDefault();
            this.pickSkill(this.state.activeIndex);
        }
    }
}
