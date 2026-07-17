import { registry } from '@web/core/registry';

/**
 * Registry of client-executed webclient tool handlers, keyed by MCP tool
 * name. Each handler has the signature `async (args, env) => result`, where
 * `env` is the webclient service environment and `result` is the object
 * posted back to the paused AI session.
 */
export const webclientClientTools = registry.category('muk_ai.client_tools');
