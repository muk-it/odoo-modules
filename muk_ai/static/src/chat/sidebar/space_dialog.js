import { Component, useRef, useState, onMounted } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { Dialog } from '@web/core/dialog/dialog';
import { SelectMenu } from '@web/core/select_menu/select_menu';

import { fontAwesomeIcons } from '@muk_ai/views/fields/icon_selector/icon_selector';

/**
 * Modal dialog editing the name, icon and default agent of a space.
 *
 * The space form lives behind an administrator menu, so this dialog is where
 * a regular user settles these.
 */
export class SpaceDialog extends Component {
    static template = 'muk_ai.SpaceDialog';
    static components = { Dialog, SelectMenu };
    static props = {
        close: Function,
        title: { type: String, optional: true },
        name: { type: String, optional: true },
        icon: { type: String, optional: true },
        agentId: { type: [Number, Boolean], optional: true },
        agents: { type: Array, optional: true },
        onConfirm: Function,
    };
    static defaultProps = {
        title: _t('Edit space'),
        name: '',
        icon: 'fa-folder-o',
        agentId: false,
        agents: [],
    };
    setup() {
        this.state = useState({
            name: this.props.name || '',
            icon: this.props.icon || 'fa-folder-o',
            agentId: this.props.agentId || false,
        });
        this.icons = fontAwesomeIcons().map((icon) => ({
            value: icon,
            label: icon.slice(3).replace(/-/g, ' '),
        }));
        this.inputRef = useRef('input');
        onMounted(() => {
            const el = this.inputRef.el;
            if (el) {
                el.focus();
                el.select();
            }
        });
    }
    get canConfirm() {
        return !!(this.state.name || '').trim();
    }
    get searchPlaceholder() {
        return _t('Search an icon...');
    }
    get iconLabel() {
        const choice = this.icons.find((entry) => entry.value === this.state.icon);
        return choice ? choice.label : this.state.icon;
    }
    onInput(ev) {
        this.state.name = ev.target.value;
    }
    onKeydown(ev) {
        if (ev.key === 'Enter' && !ev.isComposing) {
            ev.preventDefault();
            this.confirm();
        }
    }
    onIconSelect(icon) {
        this.state.icon = icon || 'fa-folder-o';
    }
    onAgentChange(ev) {
        this.state.agentId = ev.target.value ? Number(ev.target.value) : false;
    }
    confirm() {
        if (!this.canConfirm) {
            return;
        }
        this.props.onConfirm({
            name: this.state.name.trim(),
            icon: this.state.icon,
            agent_id: this.state.agentId,
        });
        this.props.close();
    }
    cancel() {
        this.props.close();
    }
}
