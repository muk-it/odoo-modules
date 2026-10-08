import { registry } from '@web/core/registry';

import { toolPayload } from '@muk_ai/core/session/turns';

/**
 * Tools the model runs in the browser, keyed by MCP tool name, as
 * `{execute: async (args, chat) => result, defer?: () => ms}`. `chat` is the
 * AI chat plugin; the result is posted back to the paused session.
 */
export const clientTools = registry.category('muk_ai.client_tools');

const handled = new Set();

/**
 * Run a registered tool and post its outcome back to the session.
 * @param {object} chat the AI chat plugin
 * @param {number} sessionId the paused session
 * @param {object} entry the `client_action` event
 */
async function execute(chat, sessionId, entry) {
    const call = (method, args, kwargs) =>
        chat.orm.silent.call(
            'muk_ai.session',
            method,
            [sessionId, entry.call_id, ...args],
            kwargs,
        );
    const args = toolPayload(entry.arguments || {});
    if (!args || typeof args !== 'object') {
        await call('reject_client_action', [], {
            reason: 'client received corrupt or truncated tool arguments',
        }).catch(() => {});
        return;
    }
    try {
        await call('submit_client_result', [
            await clientTools.get(entry.name).execute(args, chat),
        ]);
    } catch (error) {
        await call('reject_client_action', [], {
            reason: String(error?.message || error || 'client tool failed'),
        }).catch(() => {});
    }
}

/**
 * Answer a session's client action from this tab, once per browser.
 *
 * Only a tab steering the chat calls this. Two tabs can both show it, so the
 * Web Locks API elects the first; the lock is kept until the tab closes, so a
 * throttled sibling waking up later never runs the same call again.
 * @param {object} chat the AI chat plugin
 * @param {number} sessionId the paused session
 * @param {object} entry the `client_action` event
 */
export function runClientAction(chat, sessionId, entry) {
    if (
        !entry.call_id ||
        !clientTools.contains(entry.name) ||
        handled.has(entry.call_id)
    ) {
        return;
    }
    handled.add(entry.call_id);
    const run = () => {
        if (!navigator.locks?.request) {
            return execute(chat, sessionId, entry);
        }
        navigator.locks.request(
            `muk_ai.client_action.${entry.call_id}`,
            { ifAvailable: true },
            async (lock) => {
                if (lock !== null) {
                    await execute(chat, sessionId, entry);
                    await new Promise(() => {});
                }
            },
        );
    };
    const delay = clientTools.get(entry.name).defer?.() || 0;
    if (delay) {
        setTimeout(run, delay);
    } else {
        run();
    }
}
