import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';

import { toolResultFiles } from '@muk_ai/core/attachment/tool_files';

export const toolBlockDecorators = registry.category('muk_ai.tool_block_decorators');

function withAt(obj, at) {
    return at ? { ...obj, at } : obj;
}

function withEventId(obj, eventId) {
    return eventId ? { ...obj, eventId } : obj;
}

function withClientKey(obj, clientKey) {
    return clientKey ? { ...obj, clientKey } : obj;
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
            } else if (current) {
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
    for (let i = turns.length - 1; i >= 0; i--) {
        if (turns[i].role === 'assistant') {
            let lastText = -1;
            (turns[i].blocks || []).forEach((block, blockIndex) => {
                if (block.type === 'text') {
                    lastText = blockIndex;
                }
            });
            turns[i].regenerateAt = lastText;
            break;
        }
    }
    return turns;
}
