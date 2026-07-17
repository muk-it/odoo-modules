import { registry } from '@web/core/registry';

import { makeClientToolListener } from './executor';
import { webclientClientTools } from './registry';

import './adjust_search';

/**
 * Client-side executor for webclient tools (adjust_search).
 *
 * Subscribes to the AI session event bus and, whenever a session pauses on
 * a client action whose tool is registered in `muk_ai.client_tools`, runs
 * the handler against this tab's webclient and posts the result back via
 * `submit_client_result` (or `reject_client_action` on failure). Only the
 * tab holding the session's chat window answers - that tab owns the view
 * the user is talking about.
 */
export const webclientClientToolsService = {
    dependencies: ['bus_service', 'orm', 'muk_ai.chat_window'],
    /**
     * @param {object} env the service environment
     * @param {object} deps resolved dependencies ({bus_service, orm, chat window})
     * @returns {object} the (empty) public service API
     */
    start(env, { bus_service: bus, orm, 'muk_ai.chat_window': chatWindow }) {
        const onEvent = makeClientToolListener({
            orm,
            chatWindow,
            contains: (name) => webclientClientTools.contains(name),
            execute: (name, args) => webclientClientTools.get(name)(args, env),
        });
        bus.subscribe('muk_ai.event', onEvent);
        return {};
    },
};

registry.category('services').add('muk_ai.client_tools', webclientClientToolsService);
