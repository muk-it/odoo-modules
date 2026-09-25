import { registry } from '@web/core/registry';

import { kanbanView } from '@web/views/kanban/kanban_view';

registry.category('views').add('product_search_kanban', {
    ...kanbanView,
    buttonTemplate: 'muk_product.KanbanView.Buttons',
});
