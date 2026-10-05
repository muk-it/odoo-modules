import { ListController } from '@web/views/list/list_controller';

/**
 * List controller for MCP access entries, adding a button that opens the
 * model-selection wizard and reloads the list once it closes.
 */
export class AccessListController extends ListController {
    onAddModelsButton() {
        this.actionService.doAction('muk_mcp_access.action_model_selection', {
            onClose: () => this.model.load(),
        });
    }
}
