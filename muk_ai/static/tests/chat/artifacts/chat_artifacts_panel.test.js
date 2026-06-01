import { describe, expect, test } from '@odoo/hoot';
import { Component, xml } from '@odoo/owl';
import { click, queryAll, queryFirst } from '@odoo/hoot-dom';
import { mountWithCleanup, patchTranslations } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { ChatArtifactsPanel } from '@muk_ai/chat/artifacts/chat_artifacts_panel';
import '@muk_ai/chat/artifacts/types/attachments_type';

describe.current.tags('muk_ai');
defineMailModels();
patchTranslations();


function makeSession({ pendingAttachments = [], events = [] } = {}) {
    return {
        state: {
            pendingAttachments,
            events,
        },
    };
}


function mountPanel(sessionLike, opts = {}) {
    const closed = { count: 0 };
    const opened = [];
    class Parent extends Component {
        static components = { ChatArtifactsPanel };
        static props = {};
        static template = xml`
            <ChatArtifactsPanel
                session="props.session"
                onClose="() => this.props.onClose()"
                onOpenAttachment="(att) => this.props.onOpenAttachment(att)"
            />
        `;
    }
    Parent.props = {
        session: { type: Object },
        onClose: { type: Function },
        onOpenAttachment: { type: Function },
    };
    return mountWithCleanup(Parent, {
        props: {
            session: sessionLike,
            onClose: () => { closed.count += 1; },
            onOpenAttachment: (att) => opened.push(att),
        },
    }).then((parent) => ({ parent, closed, opened }));
}


test('renders attachments tab with two cards from pending + user events', async () => {
    const session = makeSession({
        pendingAttachments: [
            { id: 1, filename: 'a.png', mimetype: 'image/png' },
        ],
        events: [
            {
                kind: 'user_message',
                content: 'hello',
                attachments: [
                    { id: 2, filename: 'b.pdf', mimetype: 'application/pdf' },
                ],
            },
        ],
    });
    await mountPanel(session);
    const cards = queryAll('.mk_artifacts_panel .mk_att_card');
    expect(cards.length).toBe(2);
});


test('clicking a card forwards attachment via onOpenAttachment', async () => {
    const session = makeSession({
        events: [
            {
                kind: 'user_message',
                content: 'x',
                attachments: [
                    { id: 9, filename: 'c.txt', mimetype: 'text/plain' },
                ],
            },
        ],
    });
    const { opened } = await mountPanel(session);
    await click(queryFirst('.mk_artifacts_panel .mk_att_card'));
    expect(opened.length).toBe(1);
    expect(opened[0].id).toBe(9);
});


test('close button triggers onClose prop', async () => {
    const session = makeSession({
        pendingAttachments: [{ id: 1, filename: 'a.png', mimetype: 'image/png' }],
    });
    const { closed } = await mountPanel(session);
    await click(queryFirst('.mk_artifacts_panel .mk_artifacts_close'));
    expect(closed.count).toBe(1);
});


test('panel renders empty placeholder when no artifacts contributed', async () => {
    const session = makeSession({});
    await mountPanel(session);
    const empty = queryFirst('.mk_artifacts_panel .mk_artifacts_empty');
    expect(empty).not.toBe(null);
});


test('attachments dedupe by id across pending + events', async () => {
    const session = makeSession({
        pendingAttachments: [{ id: 5, filename: 'one.png', mimetype: 'image/png' }],
        events: [
            {
                kind: 'user_message',
                content: 'hi',
                attachments: [
                    { id: 5, filename: 'one.png', mimetype: 'image/png' },
                    { id: 6, filename: 'two.png', mimetype: 'image/png' },
                ],
            },
        ],
    });
    await mountPanel(session);
    const cards = queryAll('.mk_artifacts_panel .mk_att_card');
    expect(cards.length).toBe(2);
});
