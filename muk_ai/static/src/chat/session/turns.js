// @odoo-module

import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';

import { toolResultFiles } from '@muk_ai/core/attachment/tool_files';

export const toolBlockDecorators = registry.category('muk_ai.tool_block_decorators');

/**
 * Registry of predicates naming tool calls some other surface already draws,
 * as `(block, turn) => boolean`.
 */
export const hiddenToolBlocks = registry.category('muk_ai.hidden_tool_blocks');

/**
 * Tell whether a tool card must not be drawn because another surface draws it.
 *
 * A question and a delegation run are both tool calls, but each already has a
 * card of its own; a second card saying the same thing is noise.
 * @param {object} block the tool block
 * @param {object} turn the turn it belongs to
 * @param {object} [pendingAsk] what the session is waiting on, when it is
 * @returns {boolean} true when the tool card should be left out
 */
export function isToolBlockHidden(block, turn, pendingAsk) {
    if (hiddenToolBlocks.getAll().some((hides) => hides(block, turn))) {
        return true;
    }
    if (block.result !== null && block.result !== undefined) {
        return false;
    }
    if (pendingAsk && pendingAsk.call_id === block.callId) {
        return true;
    }
    return (turn.blocks || []).some(
        (other) => other.type === 'ask' && other.callId === block.callId,
    );
}

/**
 * Registry of transcript builders for event kinds the core does not render,
 * keyed by event kind. Each builder has the signature `(entry) => turn`,
 * where `entry` is the raw session event and `turn` is a renderable item
 * carrying the `role` a `muk_ai.turn_renderers` entry is keyed by, or
 * `null` to drop the event. The event's `at` and `event_id` are stamped
 * onto the returned turn.
 */
export const turnBuilders = registry.category('muk_ai.turn_builders');

/**
 * Registry of components drawing the turns addons build, keyed by turn
 * role. Each component receives the props `turn` and `session`.
 */
export const turnRenderers = registry.category('muk_ai.turn_renderers');

/**
 * Look up the component registered to draw a turn.
 * @param {object} turn rendered turn
 * @returns {Function|null} component class, null for a core-rendered turn
 */
export function turnRendererFor(turn) {
    return turnRenderers.get(turn.role, null);
}

function withAt(obj, at) {
    return at ? { ...obj, at } : obj;
}

function withEventId(obj, eventId) {
    return eventId ? { ...obj, eventId } : obj;
}

function withClientKey(obj, clientKey) {
    return clientKey ? { ...obj, clientKey } : obj;
}

/**
 * Read a tool block's payload, which arrives as a string or as an object.
 * @param {*} value the raw arguments or result
 * @returns {object|null} the parsed payload, null when it is not JSON
 */
export function toolPayload(value) {
    if (typeof value !== 'string') {
        return value || null;
    }
    try {
        return JSON.parse(value);
    } catch {
        return null;
    }
}

/**
 * Give a tool block the kind, icon, label and band its card should show.
 *
 * The result arrives after the block is built, so everything but the kind is
 * a getter reading the block's current arguments and result at render time.
 * Every addon that decorates a card needs exactly that, and four of them were
 * each writing it out by hand.
 * @param {object} block the tool block being built
 * @param {object} parts `kind`, plus any of `icon`, `label` and `band` as
 *     functions receiving `{args, result, pending}`. `result` is null for a
 *     call that has not answered AND for one whose answer did not survive the
 *     bus, so `pending` is what tells a band it is still waiting.
 */
export function describeToolBlock(block, parts) {
    if (parts.kind) {
        block.kind = parts.kind;
    }
    const descriptors = {};
    for (const name of ['icon', 'label', 'band']) {
        const build = parts[name];
        if (build) {
            descriptors[name] = {
                enumerable: true,
                get() {
                    return build({
                        args: toolPayload(this.arguments) || {},
                        result: toolPayload(this.result),
                        pending: this.result === null || this.result === undefined,
                    });
                },
            };
        }
    }
    Object.defineProperties(block, descriptors);
}

function decorateToolBlock(block, entry) {
    for (const [, decorate] of toolBlockDecorators.getEntries()) {
        decorate(block, entry);
    }
}

function addTurnSources(turn, sources) {
    const list = turn.sources || (turn.sources = []);
    const seen = turn._sourceIds || (turn._sourceIds = new Set());
    for (const source of sources) {
        if (source && source.id && !seen.has(source.id)) {
            seen.add(source.id);
            list.push(source);
        }
    }
}

/**
 * Append the files a tool produced to an assistant turn, without duplicates.
 * @param {object} turn assistant turn being built
 * @param {Array} files attachment descriptors
 */
function addTurnAttachments(turn, files) {
    if (!files.length) {
        return;
    }
    const list = turn.attachments || (turn.attachments = []);
    const seen = turn._attachmentIds || (turn._attachmentIds = new Set());
    for (const file of files) {
        if (!seen.has(file.id)) {
            seen.add(file.id);
            list.push(file);
        }
    }
}

/**
 * Fold a flat session event log into grouped, renderable conversation turns.
 * Merges consecutive assistant blocks, attaches tool results to their calls,
 * and flags turns preceding the last /clear or /compact boundary as history.
 * @param {Array} log ordered session events
 * @returns {Array} rendered turns
 */
export function buildRenderedTurns(log) {
    const turns = [];
    let current = null;
    const toolsByCallId = {};
    for (const entry of log || []) {
        const at = entry.at || null;
        const eventId = entry.event_id || null;
        if (entry.kind === 'user_message') {
            turns.push(
                withClientKey(
                    withEventId(
                        withAt(
                            {
                                role: 'user',
                                text: entry.content,
                                attachments: entry.attachments || [],
                            },
                            at,
                        ),
                        eventId,
                    ),
                    entry._clientKey,
                ),
            );
            current = null;
        } else if (entry.kind === 'answer') {
            turns.push(
                withClientKey(
                    withEventId(
                        withAt(
                            {
                                role: 'user',
                                text: entry.answer,
                                attachments: entry.attachments || [],
                            },
                            at,
                        ),
                        eventId,
                    ),
                    entry._clientKey,
                ),
            );
            current = null;
        } else if (entry.kind === 'tool_call') {
            if (!current) {
                current = withEventId(
                    withAt({ role: 'assistant', blocks: [] }, at),
                    eventId,
                );
                turns.push(current);
            }
            const block = withAt(
                {
                    type: 'tool',
                    name: entry.name,
                    arguments: entry.arguments,
                    callId: entry.call_id,
                    result: null,
                },
                at,
            );
            decorateToolBlock(block, entry);
            current.blocks.push(block);
            if (entry.call_id) {
                toolsByCallId[entry.call_id] = block;
            }
        } else if (entry.kind === 'tool_result') {
            const block = entry.call_id && toolsByCallId[entry.call_id];
            if (block) {
                block.result = entry.result;
            } else {
                if (!current) {
                    current = withEventId(
                        withAt({ role: 'assistant', blocks: [] }, at),
                        eventId,
                    );
                    turns.push(current);
                }
                current.blocks.push(
                    withAt(
                        {
                            type: 'tool',
                            name: entry.name,
                            arguments: null,
                            callId: entry.call_id,
                            result: entry.result,
                        },
                        at,
                    ),
                );
            }
            if (current && Array.isArray(entry.sources) && entry.sources.length) {
                addTurnSources(current, entry.sources);
            }
            if (current) {
                addTurnAttachments(current, toolResultFiles(entry.result));
            }
        } else if (entry.kind === 'text') {
            if (!current) {
                current = withEventId(
                    withAt({ role: 'assistant', blocks: [] }, at),
                    eventId,
                );
                turns.push(current);
            }
            const last = current.blocks[current.blocks.length - 1];
            if (last && last.type === 'text') {
                last.text = last.text + '\n\n' + entry.content;
            } else {
                current.blocks.push(
                    withEventId(
                        withAt({ type: 'text', text: entry.content }, at),
                        eventId,
                    ),
                );
            }
        } else if (entry.kind === 'ask_user') {
            if (!current) {
                current = withEventId(
                    withAt({ role: 'assistant', blocks: [] }, at),
                    eventId,
                );
                turns.push(current);
            }
            current.blocks.push(
                withAt(
                    {
                        type: 'ask',
                        text: entry.text,
                        options: entry.options,
                        preview: entry.preview || null,
                        callId: entry.call_id,
                        resolution: entry.resolution || 'text',
                    },
                    at,
                ),
            );
        } else if (entry.kind === 'command') {
            turns.push(
                withAt(
                    {
                        role: 'command',
                        name: entry.name || '',
                        message: entry.message || '',
                        summary: entry.summary || '',
                        originalMessages: entry.original_messages || 0,
                        originalTokens: entry.original_tokens || 0,
                    },
                    at,
                ),
            );
            current = null;
        } else if (entry.kind === 'agent_switched') {
            const toAgent = entry.agent_name || _t('default agent');
            turns.push(
                withAt(
                    {
                        role: 'command',
                        name: 'agent',
                        message: entry.from_agent_name
                            ? _t('%s → %s', entry.from_agent_name, toAgent)
                            : _t('Switched to %s', toAgent),
                    },
                    at,
                ),
            );
            current = null;
        } else if (entry.kind === 'compact_progress') {
            turns.push(
                withAt(
                    {
                        role: 'compact_progress',
                        eventId: entry.event_id || null,
                        state: entry.state || 'streaming',
                        auto: !!entry.auto,
                        messageCount: entry.message_count || 0,
                        tokensEstimate: entry.tokens_estimate || 0,
                        streamedText: entry.streamed_text || '',
                        summary: entry.summary || '',
                        originalMessages: entry.original_messages || 0,
                        originalTokens: entry.original_tokens || 0,
                        message: entry.message || '',
                        error: entry.error || '',
                    },
                    at,
                ),
            );
            current = null;
        } else {
            const build = turnBuilders.get(entry.kind, null);
            const turn = build && build(entry);
            if (turn) {
                turns.push(withEventId(withAt(turn, at), eventId));
                current = null;
            }
        }
    }
    let lastBoundary = -1;
    for (let i = turns.length - 1; i >= 0; i--) {
        const turn = turns[i];
        const isClearOrCompact =
            turn.role === 'command' &&
            (turn.name === '/clear' || turn.name === '/compact');
        const isCompactBoundary =
            turn.role === 'compact_progress' &&
            (turn.state === 'streaming' || turn.state === 'done');
        if (isClearOrCompact || isCompactBoundary) {
            lastBoundary = i;
            break;
        }
    }
    if (lastBoundary > 0) {
        for (let i = 0; i < lastBoundary; i++) {
            turns[i].inHistory = true;
        }
    }
    // Where the answer ends, on every assistant turn: a band or a button that
    // belongs under the answer would otherwise repeat under each text block.
    for (const turn of turns) {
        if (turn.role !== 'assistant') {
            continue;
        }
        let lastText = -1;
        (turn.blocks || []).forEach((block, blockIndex) => {
            if (block.type === 'text') {
                lastText = blockIndex;
            }
        });
        turn.lastTextAt = lastText;
    }
    for (let i = turns.length - 1; i >= 0; i--) {
        if (turns[i].role === 'assistant') {
            turns[i].regenerateAt = turns[i].lastTextAt;
            break;
        }
    }
    return turns;
}
