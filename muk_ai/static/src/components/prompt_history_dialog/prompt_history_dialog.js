import { Component, onWillStart, proxy, t, useProps, usePlugin } from '@odoo/owl';

import { Dialog } from '@web/core/dialog/dialog';
import { DialogPlugin } from '@web/core/dialog/dialog_plugin';
import { _t } from '@web/core/l10n/translation';
import { ORM } from '@web/core/orm_plugin';
import { registry } from '@web/core/registry';
import { ActionPlugin } from '@web/webclient/actions/action_plugin';

import { renderMarkdown } from '@muk_ai/core/markdown/markdown';
import { formatTimestamp } from '@muk_ai/core/utils/utils';

/** Dialog listing the revisions of a prompt field, with their diff and a restore. */
export class PromptHistoryDialog extends Component {
    static template = 'muk_ai.PromptHistoryDialog';
    static components = { Dialog };
    props = useProps({
        close: t.function(),
        resModel: t.string(),
        resId: t.number(),
        fieldName: t.string(),
        fieldLabel: t.string(),
    });
    orm = usePlugin(ORM);
    action = usePlugin(ActionPlugin);
    state = proxy({ entries: [], index: null, diff: '' });
    formatTimestamp = formatTimestamp;
    setup() {
        onWillStart(async () => {
            const [record] = await this.orm.read(
                this.props.resModel,
                [this.props.resId],
                ['prompt_history_metadata'],
            );
            this.state.entries =
                record?.prompt_history_metadata?.[this.props.fieldName] || [];
            if (this.state.entries.length) {
                await this.select(0);
            }
        });
    }
    get title() {
        return _t('%s: History', this.props.fieldLabel);
    }
    get diff() {
        const diff = this.state.diff.trim();
        return diff
            ? renderMarkdown(['```diff', diff, '```'].join('\n'))
            : _t('No differences.');
    }
    async select(index) {
        const { resModel, resId, fieldName } = this.props;
        this.state.index = index;
        this.state.diff = await this.orm.call(resModel, 'prompt_history_unified_diff', [
            resId,
            fieldName,
            index,
        ]);
    }
    async restore() {
        const { resModel, resId, fieldName } = this.props;
        const action = await this.orm.call(resModel, 'prompt_history_restore', [
            resId,
            fieldName,
            this.state.index,
        ]);
        if (action) {
            this.action.doAction(action);
        }
        this.props.close();
    }
}

registry.category('actions').add('muk_ai.prompt_history_dialog', (env, action) => {
    const params = action.params || {};
    usePlugin(DialogPlugin).add(PromptHistoryDialog, {
        resModel: params.res_model,
        resId: params.res_id,
        fieldName: params.field_name,
        fieldLabel: params.field_label || _t('Field'),
    });
    return { type: 'ir.actions.act_window_close' };
});
