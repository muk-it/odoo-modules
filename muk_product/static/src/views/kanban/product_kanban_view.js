/** @odoo-module **/

import { registry } from '@web/core/registry';

import { kanbanView } from '@web/views/kanban/kanban_view';
import { ProductKanbanController } from "@muk_product/views/kanban/product_kanban_controller";

registry.category('views').add('product_search_kanban', {
    ...kanbanView,
    Controller: ProductKanbanController,
    buttonTemplate: 'muk_product.KanbanView.Buttons',
});

