import { Component, proxy, t, useOnChange, useProps, xml } from '@odoo/owl';

import { useFileViewer } from '@web/core/file_viewer/file_viewer_hook';
import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';

import { AttachmentCard, toFileModel } from '@muk_ai/core/attachment/attachment';
import { SourceList } from '@muk_ai/chat/sources/sources';

const INLINE_IMAGE = /!\[([^\]]*)\]\(\/web\/image\/(\d+)\)/g;

/**
 * Tabs of the artifacts panel, keyed by id, as `{label, icon, component,
 * collect(session)}`. A tab shows when `collect` finds items; its component
 * receives `items`, `session` and `focusItemId`.
 */
export const artifactTypes = registry.category('muk_ai.artifact_types');

/**
 * Keep the items whose id was not seen before.
 * @param {Array} items the items
 * @returns {Array} the items without duplicates
 */
function unique(items) {
    const seen = new Set();
    return items.filter((item) => item?.id && !seen.has(item.id) && seen.add(item.id));
}

/** Artifacts tab listing the files of a chat. */
class AttachmentsTab extends Component {
    static template = 'muk_ai.AttachmentsTab';
    static components = { AttachmentCard };
    props = useProps({
        items: t.array(),
        session: t.object(),
        focusItemId: t.any().optional(),
    });
    fileViewer = useFileViewer();
    open(attachment) {
        this.fileViewer.open(toFileModel(attachment));
    }
}

/** Artifacts tab listing the sources a chat cited. */
class SourcesTab extends Component {
    static template = xml`<SourceList sources="this.props.items" sessionId="this.props.session.id" focusItemId="this.props.focusItemId"/>`;
    static components = { SourceList };
    props = useProps({
        items: t.array(),
        session: t.object(),
        focusItemId: t.any().optional(),
    });
}

/** Side panel grouping what a chat produced and cited into tabs. */
export class ArtifactsPanel extends Component {
    static template = 'muk_ai.ArtifactsPanel';
    props = useProps({
        session: t.object(),
        focus: t.object().optional(),
        onClose: t.function(),
    });
    state = proxy({ tab: null, itemId: null });
    setup() {
        useOnChange(
            () => [this.props.focus],
            (focus) =>
                focus &&
                Object.assign(this.state, {
                    tab: focus.tab,
                    itemId: focus.itemId ?? null,
                }),
        );
    }
    get tabs() {
        return artifactTypes
            .getEntries()
            .map(([id, type]) => ({
                ...type,
                id,
                items: type.collect(this.props.session),
            }))
            .filter((tab) => tab.items.length);
    }
    get active() {
        const tabs = this.tabs;
        return tabs.find((tab) => tab.id === this.state.tab) || tabs[0];
    }
}

artifactTypes
    .add(
        'attachments',
        {
            label: _t('Attachments'),
            icon: 'attach_file',
            component: AttachmentsTab,
            collect: (session) =>
                unique([
                    ...session.state.attachments,
                    ...session.turns.flatMap((turn) => [
                        ...(turn.attachments || []),
                        ...(turn.blocks || [])
                            .filter((block) => block.type === 'text')
                            .flatMap((block) => [...block.text.matchAll(INLINE_IMAGE)])
                            .map(([, name, id]) => ({
                                id: Number(id),
                                filename: name || 'generated.png',
                                mimetype: 'image/png',
                            })),
                    ]),
                ]),
        },
        { sequence: 10 },
    )
    .add(
        'sources',
        {
            label: _t('Sources'),
            icon: 'link',
            component: SourcesTab,
            collect: (session) =>
                unique(session.turns.flatMap((turn) => turn.sources || [])),
        },
        { sequence: 20 },
    );
