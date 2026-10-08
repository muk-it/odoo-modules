import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';

const MAX_RESULT_DEPTH = 4;

/**
 * Registry of `(block, entry) => void` functions decorating tool blocks as
 * they are built, usually through `describeToolBlock`.
 */
export const toolBlockDecorators = registry.category('muk_ai.tool_block_decorators');

/**
 * Registry of `(block, turn) => boolean` predicates naming tool calls another
 * card already draws.
 */
export const hiddenToolBlocks = registry.category('muk_ai.hidden_tool_blocks');

/**
 * Registry of `(entry) => turn` builders for event kinds the core does not
 * draw. The turn carries the `role` its `muk_ai.turn_renderers` entry is keyed
 * by, or the builder returns null to drop the event.
 */
export const turnBuilders = registry.category('muk_ai.turn_builders');

/**
 * Registry of components drawing the turns addons build, keyed by role. Each
 * receives the props `turn` and `session`.
 */
export const turnRenderers = registry.category('muk_ai.turn_renderers');

/**
 * Read a tool payload, which arrives as a JSON string or as an object.
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
 * Tell whether a tool block's result reports a failure.
 * @param {object} block the tool block
 * @returns {boolean} true when the result carries an error marker
 */
export function toolBlockHasError(block) {
    const result = toolPayload(block.result);
    return Boolean(
        result && typeof result === 'object' && (result.error || result.ok === false),
    );
}

/**
 * Give a tool block the kind, icon, label and band its card shows.
 *
 * Everything but the kind is a getter reading the block's arguments and
 * result at render time, as the result arrives after the block is built.
 * @param {object} block the tool block being built
 * @param {object} parts `kind`, plus `icon`, `label` and `band` as functions
 *     of `{args, result, pending}`
 */
export function describeToolBlock(block, parts) {
    if (parts.kind) {
        block.kind = parts.kind;
    }
    for (const name of ['icon', 'label', 'band']) {
        if (parts[name]) {
            Object.defineProperty(block, name, {
                enumerable: true,
                get() {
                    return parts[name]({
                        args: toolPayload(this.arguments) || {},
                        result: toolPayload(this.result),
                        pending: this.result === null || this.result === undefined,
                    });
                },
            });
        }
    }
}

/**
 * Tell whether a tool card must stay out because another card draws it.
 * @param {object} block the tool block
 * @param {object} turn the turn it belongs to
 * @param {object} [pendingAsk] what the session waits on
 * @returns {boolean} true when the card is left out
 */
export function isToolBlockHidden(block, turn, pendingAsk) {
    if (hiddenToolBlocks.getAll().some((hides) => hides(block, turn))) {
        return true;
    }
    if (block.result !== null && block.result !== undefined) {
        return false;
    }
    return (
        pendingAsk?.call_id === block.callId ||
        !!pendingAsk?.actions?.some(
            (action) => !action.done && action.call_id === block.callId,
        ) ||
        turn.blocks.some(
            (other) => other.type === 'ask' && other.callId === block.callId,
        )
    );
}

/**
 * Collect the files a tool result stored, wherever they sit in it.
 * @param {*} value the tool result, at any nesting level
 * @param {Array} [out] the descriptors collected so far
 * @param {number} [depth] the current nesting level
 * @returns {Array} `{id, filename, mimetype}` descriptors
 */
export function toolResultFiles(value, out = [], depth = 0) {
    if (!value || depth > MAX_RESULT_DEPTH) {
        return out;
    }
    if (typeof value === 'string') {
        return value.includes('attachment_id')
            ? toolResultFiles(toolPayload(value), out, depth + 1)
            : out;
    }
    if (typeof value === 'object') {
        const id = value.attachment_id;
        if (Number.isInteger(id) && !out.some((file) => file.id === id)) {
            out.push({
                id,
                filename: value.filename || 'download',
                mimetype: value.mimetype || '',
            });
        }
        for (const nested of Object.values(value)) {
            toolResultFiles(nested, out, depth + 1);
        }
    }
    return out;
}

/**
 * Append items to a list, skipping those whose id is already in it.
 * @param {Array} list the list to grow
 * @param {Array} items the items to add
 */
function addUnique(list, items) {
    for (const item of items) {
        if (item?.id && !list.some((known) => known.id === item.id)) {
            list.push(item);
        }
    }
}

/**
 * Fold a session's event log into the turns a transcript draws.
 *
 * Consecutive assistant events merge into one turn, results attach to their
 * calls, and every turn before the last clear or compaction is marked as
 * history.
 * @param {Array} log the ordered session events
 * @returns {Array} the turns
 */
export function buildRenderedTurns(log) {
    const turns = [];
    const calls = {};
    const asks = {};
    let current = null;
    const stamp = (item, entry, withId = true) =>
        Object.assign(
            item,
            entry.at ? { at: entry.at } : {},
            withId && entry.event_id ? { eventId: entry.event_id } : {},
        );
    const push = (turn) => {
        turns.push(turn);
        current = null;
    };
    const assistant = (entry) => {
        if (!current) {
            current = stamp(
                { role: 'assistant', blocks: [], sources: [], attachments: [] },
                entry,
            );
            turns.push(current);
        }
        return current;
    };
    for (const entry of log || []) {
        if (entry.kind === 'user_message' || entry.kind === 'answer') {
            push(
                stamp(
                    {
                        role: 'user',
                        text: entry.kind === 'answer' ? entry.answer : entry.content,
                        attachments: entry.attachments || [],
                        clientKey: entry._clientKey,
                    },
                    entry,
                ),
            );
        } else if (entry.kind === 'tool_call') {
            const block = stamp(
                {
                    type: 'tool',
                    name: entry.name,
                    arguments: entry.arguments,
                    callId: entry.call_id,
                    result: null,
                },
                entry,
                false,
            );
            for (const decorate of toolBlockDecorators.getAll()) {
                decorate(block, entry);
            }
            assistant(entry).blocks.push(block);
            calls[entry.call_id] = block;
        } else if (entry.kind === 'tool_result') {
            const turn = assistant(entry);
            const block = entry.call_id && calls[entry.call_id];
            if (block) {
                block.result = entry.result;
            } else {
                turn.blocks.push(
                    stamp(
                        {
                            type: 'tool',
                            name: entry.name,
                            arguments: null,
                            callId: entry.call_id,
                            result: entry.result,
                        },
                        entry,
                        false,
                    ),
                );
            }
            addUnique(turn.sources, entry.sources || []);
            addUnique(turn.attachments, toolResultFiles(entry.result));
        } else if (entry.kind === 'text') {
            const blocks = assistant(entry).blocks;
            const last = blocks.at(-1);
            if (last?.type === 'text') {
                last.text = `${last.text}\n\n${entry.content}`;
            } else {
                blocks.push(stamp({ type: 'text', text: entry.content }, entry));
            }
        } else if (entry.kind === 'ask_user') {
            asks[entry.call_id] = stamp(
                {
                    type: 'ask',
                    text: entry.text,
                    options: entry.options || [],
                    preview: entry.preview || null,
                    callId: entry.call_id,
                    resolution: entry.resolution || 'text',
                },
                entry,
                false,
            );
            assistant(entry).blocks.push(asks[entry.call_id]);
        } else if (entry.kind === 'approval' && asks[entry.call_id]) {
            asks[entry.call_id].decision = entry.decision;
        } else if (entry.kind === 'command') {
            push(
                stamp(
                    {
                        role: 'command',
                        name: entry.name || '',
                        message: entry.message || '',
                        summary: entry.summary || '',
                        originalMessages: entry.original_messages || 0,
                        originalTokens: entry.original_tokens || 0,
                    },
                    entry,
                    false,
                ),
            );
        } else if (entry.kind === 'agent_switched') {
            const target = entry.agent_name || _t('default agent');
            const message = entry.from_agent_name
                ? _t('%s → %s', entry.from_agent_name, target)
                : _t('Switched to %s', target);
            push(stamp({ role: 'command', name: 'agent', message }, entry, false));
        } else if (entry.kind === 'compact_progress') {
            push(
                stamp(
                    {
                        role: 'compact_progress',
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
                    entry,
                ),
            );
        } else {
            const turn = turnBuilders.get(entry.kind, () => null)(entry);
            if (turn) {
                push(stamp(turn, entry));
            }
        }
    }
    const boundary = turns.findLastIndex(
        (turn) =>
            (turn.role === 'command' && ['/clear', '/compact'].includes(turn.name)) ||
            (turn.role === 'compact_progress' &&
                ['streaming', 'done'].includes(turn.state)),
    );
    turns.slice(0, Math.max(boundary, 0)).forEach((turn) => (turn.inHistory = true));
    for (const turn of turns) {
        if (turn.role === 'assistant') {
            turn.lastTextAt = turn.blocks.findLastIndex(
                (block) => block.type === 'text',
            );
        }
    }
    const last = turns.findLast((turn) => turn.role === 'assistant');
    if (last) {
        last.regenerateAt = last.lastTextAt;
    }
    return turns;
}

/**
 * Fold an assistant turn's blocks into the items it draws, clustering runs of
 * two or more visible tool calls into one group.
 * @param {Array} blocks the turn's blocks
 * @param {Function} isHidden predicate leaving a tool block out of clusters
 * @returns {Array} `{type, key, block, blockIndex}` items, groups carry `tools`
 */
export function buildTurnItems(blocks, isHidden) {
    const items = [];
    let group = [];
    const flush = () => {
        if (group.length === 1) {
            items.push({ ...group[0], type: 'tool' });
        } else if (group.length) {
            items.push({
                type: 'group',
                key: `g-${group[0].blockIndex}`,
                tools: group,
            });
        }
        group = [];
    };
    blocks.forEach((block, blockIndex) => {
        const item = {
            type: block.type,
            key: `${block.type[0]}-${blockIndex}`,
            block,
            blockIndex,
        };
        if (block.type === 'tool' && !isHidden(block)) {
            group.push(item);
            return;
        }
        flush();
        items.push(item);
    });
    flush();
    return items;
}
