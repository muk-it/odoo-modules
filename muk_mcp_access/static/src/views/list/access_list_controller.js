/** @odoo-module */

import { useService } from '@web/core/utils/hooks';

import { ListController } from '@web/views/list/list_controller';

export class AccessListController extends ListController {
    setup() {
        super.setup();
        this.actionService = useService('action');
    }
    onAddModelsButton() {
        this.actionService.doAction(
            'muk_mcp_access.action_model_selection',
        );
    }
}
