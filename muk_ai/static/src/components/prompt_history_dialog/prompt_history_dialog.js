import { Component, onWillStart, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { Dialog } from '@web/core/dialog/dialog';
import { useService } from '@web/core/utils/hooks';

/** Dialog showing a prompt field's revision history with diff and restore. */
export class PromptHistoryDialog extends Component {
    static template = 'muk_ai.PromptHistoryDialog';
    static components = { Dialog };
    static props = {
        close: Function,
        resModel: String,
        resId: Number,
        fieldName: String,
        fieldLabel: String,
    };
    setup() {
        this.orm = useService('orm');
        this.action = useService('action');
        this.notification = useService('notification');
        this.state = useState({
            entries: [],
            selectedIndex: null,
            diffLines: [],
            loading: true,
        });
        onWillStart(async () => {
            await this._loadHistory();
        });
    }
    get title() {
        return _t('%s — History', this.props.fieldLabel);
    }
    async _loadHistory() {
        this.state.loading = true;
        const records = await this.orm.read(
            this.props.resModel,
            [this.props.resId],
            ['prompt_history_metadata'],
        );
        const meta = (records[0] && records[0].prompt_history_metadata) || {};
        const entries = meta[this.props.fieldName] || [];
        this.state.entries = entries.map((entry, index) => ({ ...entry, index }));
        this.state.loading = false;
        if (this.state.entries.length) {
            await this.selectRevision(0);
        } else {
            this.state.selectedIndex = null;
            this.state.diffLines = [];
        }
    }
    async selectRevision(index) {
        this.state.selectedIndex = index;
        const diff = await this.orm.call(
            this.props.resModel,
            'prompt_history_unified_diff',
            [this.props.resId, this.props.fieldName, index],
        );
        this.state.diffLines = this._parseDiff(diff);
    }
    _parseDiff(raw) {
        if (!raw || !raw.trim()) {
            return [{ kind: 'empty', text: _t('No differences.') }];
        }
        return raw.split('\n').map((text) => {
            if (text.startsWith('+++') || text.startsWith('---')) {
                return { kind: 'meta', text };
            }
            if (text.startsWith('@@')) {
                return { kind: 'hunk', text };
            }
            if (text.startsWith('+')) {
                return { kind: 'added', text };
            }
            if (text.startsWith('-')) {
                return { kind: 'removed', text };
            }
            return { kind: 'context', text };
        });
    }
    formatDate(value) {
        if (!value) {
            return '';
        }
        try {
            return new Date(value).toLocaleString();
        } catch {
            return value;
        }
    }
    async onRestore() {
        if (this.state.selectedIndex === null) {
            return;
        }
        const action = await this.orm.call(
            this.props.resModel,
            'prompt_history_restore',
            [this.props.resId, this.props.fieldName, this.state.selectedIndex],
        );
        if (action) {
            this.action.doAction(action);
        }
        this.props.close();
    }
}

registry.category('actions').add('muk_ai.prompt_history_dialog', (env, action) => {
    const params = action.params || {};
    env.services.dialog.add(PromptHistoryDialog, {
        resModel: params.res_model,
        resId: params.res_id,
        fieldName: params.field_name,
        fieldLabel: params.field_label || _t('Field'),
    });
    return { type: 'ir.actions.act_window_close' };
});
