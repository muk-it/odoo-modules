import { Component, useRef, useState, onMounted } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { Dialog } from '@web/core/dialog/dialog';

/** Modal dialog prompting for a new session name. */
export class RenameDialog extends Component {
    static template = 'muk_ai.RenameDialog';
    static components = { Dialog };
    static props = {
        close: Function,
        title: { type: String, optional: true },
        initial: { type: String, optional: true },
        placeholder: { type: String, optional: true },
        onConfirm: Function,
    };
    static defaultProps = {
        title: _t('Rename chat'),
        initial: '',
        placeholder: _t('Chat name'),
    };
    setup() {
        this.state = useState({ value: this.props.initial || '' });
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
        const v = (this.state.value || '').trim();
        return !!v && v !== this.props.initial;
    }
    onInput(ev) {
        this.state.value = ev.target.value;
    }
    onKeydown(ev) {
        if (ev.key === 'Enter' && !ev.isComposing) {
            ev.preventDefault();
            this.confirm();
        }
    }
    confirm() {
        if (!this.canConfirm) {
            return;
        }
        this.props.onConfirm(this.state.value.trim());
        this.props.close();
    }
    cancel() {
        this.props.close();
    }
}
