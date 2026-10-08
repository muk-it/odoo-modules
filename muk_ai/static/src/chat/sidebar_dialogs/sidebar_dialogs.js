import { Component, onMounted, proxy, signal, t, useProps } from '@odoo/owl';

import { Dialog } from '@web/core/dialog/dialog';
import { _t } from '@web/core/l10n/translation';
import { Many2XAutocomplete } from '@web/views/fields/relational_utils';

import { IconPicker } from '@muk_ai/views/fields/icon_selector/icon_selector';

/** Dialog naming a chat; Enter saves, Save waits for a change. */
export class RenameDialog extends Component {
    static template = 'muk_ai.RenameDialog';
    static components = { Dialog };
    props = useProps({
        close: t.function(),
        initial: t.string().optional(''),
        onConfirm: t.function(),
    });
    input = signal.ref();
    state = proxy({ name: this.props.initial });
    setup() {
        onMounted(() => this.input()?.select());
    }
    get canSave() {
        const name = this.state.name.trim();
        return !!name && name !== this.props.initial;
    }
    save() {
        if (this.canSave) {
            this.props.onConfirm(this.state.name.trim());
            this.props.close();
        }
    }
}

/**
 * Dialog editing a space's name, icon, default agent and instructions, the
 * settings a regular user owns; Enter in the name saves, Save waits for a
 * change.
 */
export class SpaceDialog extends Component {
    static template = 'muk_ai.SpaceDialog';
    static components = { Dialog, IconPicker, Many2XAutocomplete };
    props = useProps({
        close: t.function(),
        space: t.object(),
        onConfirm: t.function(),
    });
    input = signal.ref();
    state = proxy({
        name: this.props.space.name || '',
        icon: this.props.space.icon || 'folder',
        agentId: this.props.space.agent_id || false,
        agentName: this.props.space.agent_name || '',
        instructions: this.props.space.instructions || '',
    });
    setup() {
        onMounted(() => this.input()?.select());
    }
    get values() {
        return {
            name: this.state.name.trim(),
            icon: this.state.icon,
            agent_id: this.state.agentId,
            instructions: this.state.instructions.trim(),
        };
    }
    get canSave() {
        const space = this.props.space;
        const values = this.values;
        return (
            !!values.name &&
            (values.name !== space.name ||
                values.icon !== (space.icon || 'folder') ||
                values.agent_id !== (space.agent_id || false) ||
                values.instructions !== (space.instructions || ''))
        );
    }
    get agentPicker() {
        return {
            resModel: 'muk_ai.agent',
            fieldString: _t('Default agent'),
            getDomain: () => [],
            activeActions: { create: false, createEdit: false },
            placeholder: _t('No default agent'),
            value: this.state.agentName,
            update: (records) =>
                Object.assign(this.state, {
                    agentId: records?.[0]?.id || false,
                    agentName: records?.[0]?.display_name || '',
                }),
        };
    }
    save() {
        if (this.canSave) {
            this.props.onConfirm(this.values);
            this.props.close();
        }
    }
}
