import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';

/**
 * Client action that runs a list of sub-actions sequentially.
 * @param {object} env the action environment
 * @param {object} action the action descriptor whose ``params.actions`` are executed
 * @returns {Promise<void>}
 */
export async function multiAction(env, action) {
    const actionService = useService('action');
    for (const subAction of action.params?.actions || []) {
        await actionService.doAction(subAction);
    }
}

registry.category('actions').add('multi_actions', multiAction);
