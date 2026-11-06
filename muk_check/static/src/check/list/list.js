/** @odoo-module */

import { registry } from '@web/core/registry';
import { listView } from '@web/views/list/list_view';

/**
 * A list that offers its header buttons without a selection.
 */
registry.category('views').add('mk_check_list', {
    ...listView,
    buttonTemplate: 'muk_check.ListView.Buttons',
});
