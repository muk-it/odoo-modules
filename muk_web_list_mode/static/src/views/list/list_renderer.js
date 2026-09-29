import { patch } from '@web/core/utils/patch';
import { ListRenderer, listRendererProps } from '@web/views/list/list_renderer';

import { t } from '@odoo/owl';

Object.assign(listRendererProps, {
    modeSwitch: t.object().optional(),
});

/**
 * Show the mode toggle of x2many lists in the header of the actions column.
 */
patch(ListRenderer.prototype, {
    get hasActionsColumn() {
        return super.hasActionsColumn || Boolean(this.props.modeSwitch);
    },
});
