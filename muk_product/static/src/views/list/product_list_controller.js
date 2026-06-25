import { useService } from '@web/core/utils/hooks';

import { ListController } from '@web/views/list/list_controller';

/** List controller adding a button that opens the product search wizard. */
export class ProductListController extends ListController {
    setup() {
        super.setup();
        this.actionService = useService('action');
    }
    onProductSearchButton(_record) {
        this.actionService.doAction('muk_product.action_product_search');
    }
}
