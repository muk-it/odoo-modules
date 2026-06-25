import { useService } from '@web/core/utils/hooks';

import { KanbanController } from '@web/views/kanban/kanban_controller';

/** Kanban controller adding a button that opens the product search wizard. */
export class ProductKanbanController extends KanbanController {
    setup() {
        super.setup();
        this.actionService = useService('action');
    }
    onProductSearchButton(_record) {
        this.actionService.doAction('muk_product.action_product_search');
    }
}
