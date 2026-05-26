/** @odoo-module */

import { registry } from '@web/core/registry';

import { listView } from '@web/views/list/list_view';
import { AccessListController } from '@muk_mcp_access/views/list/access_list_controller';

registry.category('views').add('mcp_access_list', {
    ...listView,
    Controller: AccessListController,
    buttonTemplate: 'muk_mcp_access.ListView.Buttons',
});
