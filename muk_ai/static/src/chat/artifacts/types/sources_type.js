import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';

import { SourcesTab } from '@muk_ai/chat/artifacts/types/sources_tab';

/**
 * Collect the session's cited sources from tool-result events.
 * Each server-derived ``event.sources`` entry is a source descriptor
 * (web page or record); descriptors are unioned in order and deduped by id.
 * @param {object} sessionState the client session state
 * @returns {Array} ordered, deduped source descriptors
 */
function collectSources(sessionState) {
    if (!sessionState) {
        return [];
    }
    const seen = new Set();
    const out = [];
    for (const event of sessionState.events || []) {
        if (!event || event.kind !== 'tool_result' || !event.sources) {
            continue;
        }
        for (const source of event.sources) {
            if (!source || !source.id || seen.has(source.id)) {
                continue;
            }
            seen.add(source.id);
            out.push(source);
        }
    }
    return out;
}

registry.category('muk_ai.artifact_types').add(
    'sources',
    {
        id: 'sources',
        label: _t('Sources'),
        icon: 'fa-link',
        sequence: 20,
        component: SourcesTab,
        collect: collectSources,
    },
    { force: true },
);

export { collectSources };
