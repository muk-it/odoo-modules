import {
    Component,
    proxy,
    signal,
    t,
    useEffect,
    useListener,
    useProps,
} from '@odoo/owl';

import { hasTouch } from '@web/core/browser/feature_detection';
import { _t } from '@web/core/l10n/translation';

import { ChatComposer } from '@muk_ai/chat/composer/composer';
import { slashCommands } from '@muk_ai/core/session/session';

import {
    invokeSkill,
    recentSkillNames,
    skillScopeSatisfied,
} from '@muk_ai_skills/chat/skills/skills';

/**
 * Composer button opening a searchable list of the chat's skills, recently
 * used first, with the skills the open screen does not satisfy greyed out.
 * Picking one puts its slash command in front of the composer text; one
 * named like a built-in command runs at once, with that text.
 */
export class SkillsMenu extends Component {
    static template = 'muk_ai_skills.SkillsMenu';
    props = useProps({ session: t.object(), onPick: t.function() });
    root = signal.ref();
    search = signal.ref();
    state = proxy({ open: false, filter: '', active: 0 });
    setup() {
        this.state.open = Boolean(this.props.session.state.skillsOpen);
        useEffect(() => {
            if (!this.state.open) {
                this.props.session.state.skillsOpen = false;
            }
        });
        useListener(document, 'mousedown', (ev) => {
            if (this.state.open && !this.root()?.contains(ev.target)) {
                this.state.open = false;
            }
        });
        useEffect(() => {
            if (this.open && !hasTouch()) {
                this.search()?.focus();
            }
        });
    }
    get skills() {
        return this.props.session.data.skills || [];
    }
    get open() {
        return (
            this.state.open &&
            !this.props.session.state.input.trimStart().startsWith('/')
        );
    }
    get matching() {
        const filter = this.state.filter.trim().toLowerCase();
        return this.skills.filter((skill) =>
            `${skill.label} ${skill.name} ${skill.description}`
                .toLowerCase()
                .includes(filter),
        );
    }
    get entries() {
        const viewContext = this.props.session.data.view_context;
        const available = this.matching.filter((skill) =>
            skillScopeSatisfied(skill, viewContext),
        );
        const used = recentSkillNames()
            .map((name) => available.find((skill) => skill.name === name))
            .filter(Boolean);
        const rest = available.filter((skill) => !used.includes(skill));
        return [
            ...used.map((skill, i) => ({ skill, group: i ? '' : _t('Recently used') })),
            ...rest.map((skill, i) => ({ skill, group: i ? '' : _t('All skills') })),
        ];
    }
    get locked() {
        const viewContext = this.props.session.data.view_context;
        return this.matching.filter(
            (skill) => !skillScopeSatisfied(skill, viewContext),
        );
    }
    toggle() {
        Object.assign(this.state, { open: !this.state.open, filter: '', active: 0 });
        if (this.state.open && hasTouch()) {
            document.activeElement?.blur();
        }
    }
    onFilterInput(ev) {
        Object.assign(this.state, { filter: ev.target.value, active: 0 });
    }
    pick(index) {
        const entry = this.entries[index];
        if (entry) {
            const { session } = this.props;
            const { name } = entry.skill;
            const text = session.state.input.trim();
            this.state.open = false;
            if (slashCommands.contains(`/${name}`)) {
                session.state.input = '';
                invokeSkill(session, name, text);
            } else {
                session.state.input = `/${name} ${text}`;
                document.activeElement?.blur();
                this.props.onPick();
            }
        }
    }
    onKeydown(ev) {
        const count = this.entries.length;
        if (ev.key === 'Escape') {
            this.state.open = false;
        } else if (count && ['ArrowDown', 'ArrowUp'].includes(ev.key)) {
            const step = ev.key === 'ArrowDown' ? 1 : -1;
            this.state.active = (this.state.active + step + count) % count;
        } else if (ev.key === 'Enter' && !ev.isComposing) {
            this.pick(this.state.active);
        } else {
            return;
        }
        ev.preventDefault();
    }
}

ChatComposer.components = { ...ChatComposer.components, SkillsMenu };
