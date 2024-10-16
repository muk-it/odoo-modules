import { useService } from '@web/core/utils/hooks';

import { KanbanController } from '@web/views/kanban/kanban_controller';

export class ProductKanbanController extends KanbanController {
    setup() {
        super.setup();
        this.actionService = useService('action');
    }
    onProductSearchButton(record) {
        this.actionService.doAction(
        	'muk_product.action_product_search'
        );
    }
};
