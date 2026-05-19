import { registry } from '@web/core/registry';

export const toolBlockDecorators = registry.category('muk_ai.tool_block_decorators');

function withAt(obj, at) {
    return at ? { ...obj, at } : obj;
}

function withEventId(obj, eventId) {
    return eventId ? { ...obj, eventId } : obj;
}

function decorateToolBlock(block, entry) {
    for (const [, decorate] of toolBlockDecorators.getEntries()) {
        decorate(block, entry);
    }
}

export function buildRenderedTurns(log) {
    const turns = [];
    let current = null;
    const toolsByCallId = {};
    for (const entry of log || []) {
        const at = entry.at || null;
        const eventId = entry.event_id || null;
        if (entry.kind === 'user_message') {
            turns.push(withEventId(withAt({
                role: 'user',
                text: entry.content,
                attachments: entry.attachments || [],
            }, at), eventId));
            current = null;
        } else if (entry.kind === 'answer') {
            turns.push(withEventId(withAt({
                role: 'user',
                text: entry.answer,
                attachments: entry.attachments || [],
            }, at), eventId));
            current = null;
        } else if (entry.kind === 'tool_call') {
            if (!current) {
                current = withEventId(withAt({ role: 'assistant', blocks: [] }, at), eventId);
                turns.push(current);
            }
            const block = withAt({
                type: 'tool',
                name: entry.name,
                arguments: entry.arguments,
                callId: entry.call_id,
                result: null,
            }, at);
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
                current.blocks.push(withAt({
                    type: 'tool',
                    name: entry.name,
                    arguments: null,
                    callId: entry.call_id,
                    result: entry.result,
                }, at));
            }
        } else if (entry.kind === 'text') {
            if (!current) {
                current = withEventId(withAt({ role: 'assistant', blocks: [] }, at), eventId);
                turns.push(current);
            }
            const last = current.blocks[current.blocks.length - 1];
            if (last && last.type === 'text') {
                last.text = last.text + '\n\n' + entry.content;
            } else {
                current.blocks.push(withEventId(withAt({ type: 'text', text: entry.content }, at), eventId));
            }
        } else if (entry.kind === 'ask_user') {
            if (!current) {
                current = withEventId(withAt({ role: 'assistant', blocks: [] }, at), eventId);
                turns.push(current);
            }
            current.blocks.push(withAt({
                type: 'ask',
                text: entry.text,
                options: entry.options,
                preview: entry.preview || null,
                callId: entry.call_id,
                resolution: entry.resolution || 'text',
            }, at));
        } else if (entry.kind === 'command') {
            turns.push(withAt({
                role: 'command',
                name: entry.name || '',
                message: entry.message || '',
                summary: entry.summary || '',
                originalMessages: entry.original_messages || 0,
                originalTokens: entry.original_tokens || 0,
            }, at));
            current = null;
        } else if (entry.kind === 'compact_progress') {
            turns.push(withAt({
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
            }, at));
            current = null;
        }
    }
    let lastBoundary = -1;
    for (let i = turns.length - 1; i >= 0; i--) {
        const turn = turns[i];
        const isClearOrCompact = turn.role === 'command'
            && (turn.name === '/clear' || turn.name === '/compact');
        const isCompactBoundary = turn.role === 'compact_progress'
            && (turn.state === 'streaming' || turn.state === 'done');
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
    return turns;
}

