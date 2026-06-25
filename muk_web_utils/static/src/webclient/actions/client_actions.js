import { registry } from '@web/core/registry';

/**
 * Client action that runs a list of sub-actions sequentially.
 * @param {object} env the action environment
 * @param {object} action the action descriptor whose ``params.actions`` are executed
 * @returns {Promise<void>}
 */
export async function multiAction(env, action) {
    const params = action.params || {};
    const actions = params.actions || [];
    for (const action of actions) {
        await env.services.action.doAction(action);
    }
}

registry.category('actions').add('multi_actions', multiAction);
