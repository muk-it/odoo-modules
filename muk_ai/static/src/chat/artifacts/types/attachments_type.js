import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';

import { AttachmentsTab } from '@muk_ai/chat/artifacts/types/attachments_tab';
import { collectToolFiles } from '@muk_ai/core/attachment/tool_files';

const INLINE_IMAGE_MD = /!\[([^\]]*)\]\(\/web\/image\/(\d+)\)/g;
function collectAttachments(sessionState) {
    if (!sessionState) {
        return [];
    }
    const seen = new Set();
    const out = [];
    const pending = sessionState.pendingAttachments || [];
    for (const att of pending) {
        if (!att) continue;
        const key =
            att.id != null ? `id:${att.id}` : `n:${att.filename || ''}:${out.length}`;
        if (seen.has(key)) continue;
        seen.add(key);
        out.push(att);
    }
    const events = sessionState.events || [];
    for (const event of events) {
        if (!event) continue;
        const role =
            event.kind === 'user_message' || event.kind === 'answer' ? 'user' : null;
        if (role === 'user') {
            const atts = event.attachments || [];
            for (const att of atts) {
                if (!att) continue;
                const key =
                    att.id != null
                        ? `id:${att.id}`
                        : `n:${att.filename || ''}:${out.length}`;
                if (seen.has(key)) continue;
                seen.add(key);
                out.push(att);
            }
        } else if (event.kind === 'tool_result') {
            collectToolFiles(event.result, out, seen);
        } else if (event.kind === 'text' && event.content) {
            for (const match of String(event.content).matchAll(INLINE_IMAGE_MD)) {
                const key = `id:${Number(match[2])}`;
                if (seen.has(key)) continue;
                seen.add(key);
                out.push({
                    id: Number(match[2]),
                    filename: match[1] || 'generated.png',
                    mimetype: 'image/png',
                });
            }
        }
    }
    return out;
}

registry.category('muk_ai.artifact_types').add(
    'attachments',
    {
        id: 'attachments',
        label: _t('Attachments'),
        icon: 'fa-paperclip',
        sequence: 10,
        component: AttachmentsTab,
        collect: collectAttachments,
    },
    { force: true },
);

export { collectAttachments };
