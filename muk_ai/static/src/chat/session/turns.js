/** @odoo-module */

export function buildRenderedTurns(log) {
    const turns = [];
    let current = null;
    const toolsByCallId = {};
    for (const entry of log || []) {
        if (entry.kind === 'user_message') {
            turns.push({
                role: 'user',
                text: entry.content,
                attachments: entry.attachments || [],
            });
            current = null;
        } else if (entry.kind === 'answer') {
            turns.push({
                role: 'user',
                text: entry.answer,
                attachments: entry.attachments || [],
            });
            current = null;
        } else if (entry.kind === 'tool_call') {
            if (!current) {
                current = { role: 'assistant', blocks: [] };
                turns.push(current);
            }
            const block = {
                type: 'tool',
                name: entry.name,
                arguments: entry.arguments,
                callId: entry.call_id,
                result: null,
            };
            current.blocks.push(block);
            if (entry.call_id) {
                toolsByCallId[entry.call_id] = block;
            }
        } else if (entry.kind === 'tool_result') {
            const block = entry.call_id && toolsByCallId[entry.call_id];
            if (block) {
                block.result = entry.result;
            } else if (current) {
                current.blocks.push({
                    type: 'tool',
                    name: entry.name,
                    arguments: null,
                    callId: entry.call_id,
                    result: entry.result,
                });
            }
        } else if (entry.kind === 'text') {
            if (!current) {
                current = { role: 'assistant', blocks: [] };
                turns.push(current);
            }
            current.blocks.push({ type: 'text', text: entry.content });
        } else if (entry.kind === 'ask_user') {
            if (!current) {
                current = { role: 'assistant', blocks: [] };
                turns.push(current);
            }
            current.blocks.push({
                type: 'ask',
                text: entry.text,
                options: entry.options,
                preview: entry.preview || null,
                callId: entry.call_id,
                resolution: entry.resolution || 'text',
            });
        } else if (entry.kind === 'command') {
            turns.push({
                role: 'command',
                name: entry.name || '',
                message: entry.message || '',
                summary: entry.summary || '',
                originalMessages: entry.original_messages || 0,
                originalTokens: entry.original_tokens || 0,
            });
            current = null;
        }
    }
    return turns;
}

