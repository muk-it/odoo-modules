import { Component } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { Dialog } from '@web/core/dialog/dialog';

export class RevisionDialog extends Component {
    static template = 'muk_ai.RevisionDialog';
    static components = { Dialog };
    static props = {
        close: Function,
        oldLabel: String,
        newLabel: String,
        diff: String,
    };
    get title() {
        return _t('Diff: %s → %s', this.props.oldLabel, this.props.newLabel);
    }
    get lines() {
        const raw = this.props.diff || '';
        if (!raw.trim()) {
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
}

registry.category('actions').add('muk_ai.revision_dialog', (env, action) => {
    const params = action.params || {};
    env.services.dialog.add(RevisionDialog, {
        oldLabel: params.old_label || _t('Old'),
        newLabel: params.new_label || _t('New'),
        diff: params.diff || '',
    });
    return { type: 'ir.actions.act_window_close' };
});
