/** @odoo-module */

import { describe, expect, test } from '@odoo/hoot';
import { click, queryAll, queryFirst } from '@odoo/hoot-dom';
import { Component, xml } from '@odoo/owl';
import { mountWithCleanup } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import { ChatComposer } from '@muk_ai/chat/composer/chat_composer';

describe.current.tags('muk_ai');
defineMailModels();


function makeParent({
    attachments = [],
    canAttach = true,
    onAttachFiles,
    onRemoveAttachment,
    onOpenAttachment,
} = {}) {
    class Parent extends Component {
        static components = { ChatComposer };
        static props = {};
        static template = xml`
            <ChatComposer
                value="''"
                placeholder="'type'"
                canSend="false"
                canStop="false"
                canAttach="props.canAttach"
                attachments="props.attachments"
                onInput="() => {}"
                onSend="() => {}"
                onAttachFiles="props.onAttachFiles or (() => {})"
                onRemoveAttachment="props.onRemoveAttachment or (() => {})"
                onOpenAttachment="props.onOpenAttachment or (() => {})"
            />
        `;
    }
    Parent.props = {
        attachments: { type: Array },
        canAttach: { type: Boolean },
        onAttachFiles: { type: Function, optional: true },
        onRemoveAttachment: { type: Function, optional: true },
        onOpenAttachment: { type: Function, optional: true },
    };
    return {
        Parent,
        props: {
            attachments,
            canAttach,
            onAttachFiles,
            onRemoveAttachment,
            onOpenAttachment,
        },
    };
}


test('renders no cards when attachments is empty', async () => {
    const { Parent, props } = makeParent();
    await mountWithCleanup(Parent, { props });
    expect('.mk_att_card').toHaveCount(0);
    expect('.mk_attach').toHaveCount(1);
});


test('renders image thumb for image attachment', async () => {
    const { Parent, props } = makeParent({
        attachments: [
            { id: 42, filename: 'pic.png', mimetype: 'image/png', size: 1024 },
        ],
    });
    await mountWithCleanup(Parent, { props });
    expect('.mk_att_card').toHaveCount(1);
    expect('.mk_att_card_thumb').toHaveCount(1);
    expect('.mk_att_card .o_image').toHaveCount(0);
    expect(queryFirst('.mk_att_card_thumb').getAttribute('alt')).toBe('pic.png');
});


test('renders o_image tile with mimetype for pdf attachment', async () => {
    const { Parent, props } = makeParent({
        attachments: [
            { id: 7, filename: 'report.pdf', mimetype: 'application/pdf', size: 2048 },
        ],
    });
    await mountWithCleanup(Parent, { props });
    expect('.mk_att_card').toHaveCount(1);
    const img = queryFirst('.mk_att_card .o_image');
    expect(img).not.toBe(null);
    expect(img.getAttribute('data-mimetype')).toBe('application/pdf');
    expect('.mk_att_card_thumb').toHaveCount(0);
});


test('renders o_image tile with mimetype for plain text attachment', async () => {
    const { Parent, props } = makeParent({
        attachments: [
            { id: 9, filename: 'notes.txt', mimetype: 'text/plain', size: 300 },
        ],
    });
    await mountWithCleanup(Parent, { props });
    expect(queryFirst('.mk_att_card .o_image').getAttribute('data-mimetype')).toBe('text/plain');
});


test('opens attachment when clicking the card', async () => {
    let opened = null;
    const { Parent, props } = makeParent({
        attachments: [
            { id: 101, filename: 'report.pdf', mimetype: 'application/pdf', size: 2048 },
        ],
        onOpenAttachment: (attachment) => {
            opened = attachment.id;
        },
    });
    await mountWithCleanup(Parent, { props });
    await click('.mk_att_card');
    expect(opened).toBe(101);
});


test('removes attachment via the card remove button', async () => {
    let removedId = null;
    const { Parent, props } = makeParent({
        attachments: [
            { id: 101, filename: 'pic.png', mimetype: 'image/png', size: 1024 },
        ],
        onRemoveAttachment: (id) => {
            removedId = id;
        },
    });
    await mountWithCleanup(Parent, { props });
    expect('.mk_att_card_remove').toHaveCount(1);
    await click('.mk_att_card_remove');
    expect(removedId).toBe(101);
});


test('disables attach button when canAttach is false', async () => {
    const { Parent, props } = makeParent({ canAttach: false });
    await mountWithCleanup(Parent, { props });
    const label = queryAll('.mk_attach')[0];
    expect(label).not.toBe(undefined);
    expect(label.classList.contains('mk_attach_disabled')).toBe(true);
    const input = queryFirst('.mk_file_input');
    expect(input).not.toBe(null);
    expect(input.disabled).toBe(true);
});
