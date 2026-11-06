/** @odoo-module */

import { registry } from '@web/core/registry';
import { listView } from '@web/views/list/list_view';

/**
 * A list that offers the header buttons marked mk_check_always without a selection.
 */
registry.category('views').add('mk_check_list', {
    ...listView,
    buttonTemplate: 'muk_check.ListView.Buttons',
});
