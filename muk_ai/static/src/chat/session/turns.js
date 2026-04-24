function withAt(obj, at) {
    return at ? { ...obj, at } : obj;
}

export function buildRenderedTurns(log) {
    const turns = [];
    let current = null;
    const toolsByCallId = {};
    for (const entry of log || []) {
        const at = entry.at || null;
        if (entry.kind === 'user_message') {
            turns.push(withAt({
                role: 'user',
                text: entry.content,
                attachments: entry.attachments || [],
            }, at));
            current = null;
        } else if (entry.kind === 'answer') {
            turns.push(withAt({
                role: 'user',
                text: entry.answer,
                attachments: entry.attachments || [],
            }, at));
            current = null;
        } else if (entry.kind === 'tool_call') {
            if (!current) {
                current = withAt({ role: 'assistant', blocks: [] }, at);
                turns.push(current);
            }
            const block = withAt({
                type: 'tool',
                name: entry.name,
                arguments: entry.arguments,
                callId: entry.call_id,
                result: null,
            }, at);
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
                current = withAt({ role: 'assistant', blocks: [] }, at);
                turns.push(current);
            }
            current.blocks.push(withAt({ type: 'text', text: entry.content }, at));
        } else if (entry.kind === 'ask_user') {
            if (!current) {
                current = withAt({ role: 'assistant', blocks: [] }, at);
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
        }
    }
    return turns;
}

