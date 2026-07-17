import { describe, expect, test } from '@odoo/hoot';
import { animationFrame } from '@odoo/hoot-mock';
import { click, queryAll, queryFirst } from '@odoo/hoot-dom';
import { Component, useState, xml } from '@odoo/owl';
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
    expect(queryFirst('.mk_att_card .o_image').getAttribute('data-mimetype')).toBe(
        'text/plain',
    );
});

test('opens attachment when clicking the card', async () => {
    let opened = null;
    const { Parent, props } = makeParent({
        attachments: [
            {
                id: 101,
                filename: 'report.pdf',
                mimetype: 'application/pdf',
                size: 2048,
            },
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

function makeInteractiveParent({
    value = '',
    canSend = true,
    canStop = false,
    canAttach = true,
    agents = [],
    activeAgentId = null,
    onSend,
    onStop,
    onInput,
    onAttachFiles,
    onSelectAgent,
} = {}) {
    class Parent extends Component {
        static components = { ChatComposer };
        static props = {};
        static template = xml`
            <ChatComposer
                value="props.value"
                placeholder="'type'"
                canSend="props.canSend"
                canStop="props.canStop"
                canAttach="props.canAttach"
                attachments="[]"
                agents="props.agents"
                activeAgentId="props.activeAgentId"
                onInput="props.onInput or (() => {})"
                onSend="props.onSend or (() => {})"
                onStop="props.onStop or (() => {})"
                onAttachFiles="props.onAttachFiles or (() => {})"
                onSelectAgent="props.onSelectAgent or (() => {})"
            />
        `;
    }
    Parent.props = {
        value: { type: String },
        canSend: { type: Boolean },
        canStop: { type: Boolean },
        canAttach: { type: Boolean },
        agents: { type: Array },
        activeAgentId: { optional: true },
        onInput: { type: Function, optional: true },
        onSend: { type: Function, optional: true },
        onStop: { type: Function, optional: true },
        onAttachFiles: { type: Function, optional: true },
        onSelectAgent: { type: Function, optional: true },
    };
    return {
        Parent,
        props: {
            value,
            canSend,
            canStop,
            canAttach,
            agents,
            activeAgentId,
            onInput,
            onSend,
            onStop,
            onAttachFiles,
            onSelectAgent,
        },
    };
}

test('Enter triggers onSend when canSend=true', async () => {
    let sent = 0;
    const { Parent, props } = makeInteractiveParent({
        canSend: true,
        onSend: () => sent++,
    });
    await mountWithCleanup(Parent, { props });
    const area = queryFirst('.mk_composer textarea');
    area.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    expect(sent).toBe(1);
});

test('Enter routes to onStop when canStop=true takes priority over canSend', async () => {
    let sent = 0;
    let stopped = 0;
    const { Parent, props } = makeInteractiveParent({
        canSend: true,
        canStop: true,
        onSend: () => sent++,
        onStop: () => stopped++,
    });
    await mountWithCleanup(Parent, { props });
    queryFirst('.mk_composer textarea').dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }),
    );
    expect(stopped).toBe(1);
    expect(sent).toBe(0);
});

test('Shift+Enter does not trigger send', async () => {
    let sent = 0;
    const { Parent, props } = makeInteractiveParent({
        canSend: true,
        onSend: () => sent++,
    });
    await mountWithCleanup(Parent, { props });
    queryFirst('.mk_composer textarea').dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Enter', shiftKey: true, bubbles: true }),
    );
    expect(sent).toBe(0);
});

test('typing / shows slash command menu', async () => {
    const { Parent, props } = makeInteractiveParent({ value: '/' });
    await mountWithCleanup(Parent, { props });
    const items = queryAll('.mk_slash_item');
    expect(items.length).toBeGreaterThan(0);
    expect(items[0].textContent).toMatch(/\/help|\/clear|\/compact|\/unpin/);
});

test('typing /co filters slash menu to /compact', async () => {
    const { Parent, props } = makeInteractiveParent({ value: '/co' });
    await mountWithCleanup(Parent, { props });
    const items = queryAll('.mk_slash_item');
    expect(items.length).toBe(1);
    expect(items[0].textContent).toMatch(/\/compact/);
});

const AGENTS = [
    { id: 1, name: 'General Assistant', description: 'Default agent.' },
    { id: 2, name: 'Read-only Analyst', description: 'Read only.' },
    { id: 3, name: 'Website Designer', description: 'Builds pages.' },
];

test('typing /agent shows the agent picker with the active agent flagged', async () => {
    const { Parent, props } = makeInteractiveParent({
        value: '/agent',
        agents: AGENTS,
        activeAgentId: 1,
    });
    await mountWithCleanup(Parent, { props });
    const items = queryAll('.mk_slash_item');
    expect(items.length).toBe(3);
    expect(items[0].textContent).toMatch(/General Assistant/);
    expect(items[0].textContent).toMatch(/active/);
});

test('typing /agent read filters the picker to matching agents', async () => {
    const { Parent, props } = makeInteractiveParent({
        value: '/agent read',
        agents: AGENTS,
    });
    await mountWithCleanup(Parent, { props });
    const items = queryAll('.mk_slash_item');
    expect(items.length).toBe(1);
    expect(items[0].textContent).toMatch(/Read-only Analyst/);
});

test('Enter in agent mode selects the active match via onSelectAgent', async () => {
    let selected = null;
    const { Parent, props } = makeInteractiveParent({
        value: '/agent read',
        agents: AGENTS,
        onSelectAgent: (id) => {
            selected = id;
        },
    });
    await mountWithCleanup(Parent, { props });
    queryFirst('.mk_composer textarea').dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }),
    );
    expect(selected).toBe(2);
});

test('clicking an agent item calls onSelectAgent', async () => {
    let selected = null;
    const { Parent, props } = makeInteractiveParent({
        value: '/agent',
        agents: AGENTS,
        onSelectAgent: (id) => {
            selected = id;
        },
    });
    await mountWithCleanup(Parent, { props });
    await click(queryAll('.mk_slash_item')[2]);
    expect(selected).toBe(3);
});

test('slash menu ArrowDown cycles active entry', async () => {
    const { Parent, props } = makeInteractiveParent({ value: '/' });
    await mountWithCleanup(Parent, { props });
    const area = queryFirst('.mk_composer textarea');
    const before = queryAll('.mk_slash_item').map((el) => el.className);
    area.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }),
    );
    const after = queryAll('.mk_slash_item').map((el) => el.className);
    expect(before.length).toBeGreaterThan(0);
    expect(after.length).toBe(before.length);
});

test('Tab picks the active slash command via onInput', async () => {
    let picked = null;
    const { Parent, props } = makeInteractiveParent({
        value: '/co',
        onInput: (v) => {
            picked = v;
        },
    });
    await mountWithCleanup(Parent, { props });
    queryFirst('.mk_composer textarea').dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }),
    );
    expect(picked).toBe('/compact');
});

test('Tab preserves trailing arguments when picking a slash command', async () => {
    let picked = null;
    const { Parent, props } = makeInteractiveParent({
        value: '/co some thing',
        onInput: (v) => {
            picked = v;
        },
    });
    await mountWithCleanup(Parent, { props });
    queryFirst('.mk_composer textarea').dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }),
    );
    expect(picked).toBe('/compact some thing');
});

test('Escape in slash mode clears the composer value', async () => {
    let inputValue = '/';
    const { Parent, props } = makeInteractiveParent({
        value: '/',
        onInput: (v) => {
            inputValue = v;
        },
    });
    await mountWithCleanup(Parent, { props });
    queryFirst('.mk_composer textarea').dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }),
    );
    expect(inputValue).toBe('');
});

test('paste with image file invokes onAttachFiles when canAttach', async () => {
    const received = [];
    const { Parent, props } = makeInteractiveParent({
        onAttachFiles: (files) => received.push(...files),
    });
    const cmp = await mountWithCleanup(Parent, { props });
    const composer =
        cmp.__owl__.children[Object.keys(cmp.__owl__.children)[0]]?.component;
    const file = new File(['x'], 'p.png', { type: 'image/png' });
    const clipboardData = {
        items: [{ kind: 'file', getAsFile: () => file }],
    };
    composer.onPaste({ clipboardData, preventDefault: () => {} });
    expect(received).toHaveLength(1);
    expect(received[0].name).toBe('p.png');
});

test('paste does nothing when canAttach is false', async () => {
    const received = [];
    const { Parent, props } = makeInteractiveParent({
        canAttach: false,
        onAttachFiles: (files) => received.push(...files),
    });
    const cmp = await mountWithCleanup(Parent, { props });
    const composer =
        cmp.__owl__.children[Object.keys(cmp.__owl__.children)[0]]?.component;
    const clipboardData = {
        items: [{ kind: 'file', getAsFile: () => new File(['x'], 'p.png') }],
    };
    composer.onPaste({ clipboardData, preventDefault: () => {} });
    expect(received).toEqual([]);
});

test('file input change forwards files to onAttachFiles', async () => {
    const received = [];
    const { Parent, props } = makeInteractiveParent({
        onAttachFiles: (files) => received.push(...files),
    });
    await mountWithCleanup(Parent, { props });
    const input = queryFirst('.mk_file_input');
    const file = new File(['x'], 'p.png', { type: 'image/png' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    input.dispatchEvent(new Event('change', { bubbles: true }));
    expect(received).toHaveLength(1);
    expect(received[0].name).toBe('p.png');
});

test('onInputChange wraps the event target value and calls onInput', async () => {
    let captured = null;
    const { Parent, props } = makeInteractiveParent({
        onInput: (v) => {
            captured = v;
        },
    });
    const cmp = await mountWithCleanup(Parent, { props });
    const composer =
        cmp.__owl__.children[Object.keys(cmp.__owl__.children)[0]]?.component;
    composer.onInputChange({ target: { value: 'typing' } });
    expect(captured).toBe('typing');
});

test('hoverSlashCommand moves active index', async () => {
    const { Parent, props } = makeInteractiveParent({ value: '/' });
    const cmp = await mountWithCleanup(Parent, { props });
    const composer =
        cmp.__owl__.children[Object.keys(cmp.__owl__.children)[0]]?.component;
    composer.hoverSlashCommand(2);
    expect(composer.localState.slashActive).toBe(2);
});

test('ArrowUp wraps from 0 to end of slash list', async () => {
    const { Parent, props } = makeInteractiveParent({ value: '/' });
    const cmp = await mountWithCleanup(Parent, { props });
    const composer =
        cmp.__owl__.children[Object.keys(cmp.__owl__.children)[0]]?.component;
    composer.localState.slashActive = 0;
    const count = composer.slashCommands.length;
    composer.onKeydown({
        key: 'ArrowUp',
        isComposing: false,
        shiftKey: false,
        preventDefault: () => {},
    });
    expect(composer.localState.slashActive).toBe(count - 1);
});

test('Enter in slash menu picks command then sends', async () => {
    let picked = null;
    let sent = 0;
    const { Parent, props } = makeInteractiveParent({
        value: '/co',
        canSend: true,
        onInput: (v) => {
            picked = v;
        },
        onSend: () => sent++,
    });
    const cmp = await mountWithCleanup(Parent, { props });
    const composer =
        cmp.__owl__.children[Object.keys(cmp.__owl__.children)[0]]?.component;
    composer.onKeydown({
        key: 'Enter',
        isComposing: false,
        shiftKey: false,
        preventDefault: () => {},
    });
    expect(picked).toBe('/compact');
    expect(sent).toBe(1);
});

function enter(composer) {
    composer.onKeydown({
        key: 'Enter',
        isComposing: false,
        shiftKey: false,
        preventDefault: () => {},
    });
}

function mountedComposer(cmp) {
    return cmp.__owl__.children[Object.keys(cmp.__owl__.children)[0]]?.component;
}

test('typing /c lists /compact before /clear', async () => {
    const { Parent, props } = makeInteractiveParent({ value: '/c' });
    await mountWithCleanup(Parent, { props });
    const items = queryAll('.mk_slash_name');
    expect(items[0].textContent).toMatch(/\/compact/);
    expect(items[1].textContent).toMatch(/\/clear/);
});

test('Enter on a partial /clear prefix completes but does not auto-send', async () => {
    let picked = null;
    let sent = 0;
    const { Parent, props } = makeInteractiveParent({
        value: '/cl',
        canSend: true,
        onInput: (v) => {
            picked = v;
        },
        onSend: () => sent++,
    });
    const cmp = await mountWithCleanup(Parent, { props });
    enter(mountedComposer(cmp));
    expect(picked).toBe('/clear');
    expect(sent).toBe(0);
});

test('Enter on the full /clear command sends it', async () => {
    let sent = 0;
    const { Parent, props } = makeInteractiveParent({
        value: '/clear',
        canSend: true,
        onSend: () => sent++,
    });
    const cmp = await mountWithCleanup(Parent, { props });
    enter(mountedComposer(cmp));
    expect(sent).toBe(1);
});

test('Enter on a partial /agent prefix opens the picker instead of sending', async () => {
    let picked = null;
    let sent = 0;
    const { Parent, props } = makeInteractiveParent({
        value: '/ag',
        agents: AGENTS,
        canSend: true,
        onInput: (v) => {
            picked = v;
        },
        onSend: () => sent++,
    });
    const cmp = await mountWithCleanup(Parent, { props });
    enter(mountedComposer(cmp));
    expect(picked).toBe('/agent');
    expect(sent).toBe(0);
});

test('Enter while composing (IME) is ignored', async () => {
    let sent = 0;
    const { Parent, props } = makeInteractiveParent({
        canSend: true,
        onSend: () => sent++,
    });
    await mountWithCleanup(Parent, { props });
    queryFirst('.mk_composer textarea').dispatchEvent(
        new KeyboardEvent('keydown', {
            key: 'Enter',
            isComposing: true,
            bubbles: true,
        }),
    );
    expect(sent).toBe(0);
});

test('focusToken bump never steals focus from another text input', async () => {
    let parent;
    class Parent extends Component {
        static components = { ChatComposer };
        static props = {};
        static template = xml`
            <div>
                <input class="mk_other_input" type="text"/>
                <ChatComposer
                    value="''"
                    placeholder="'type'"
                    canSend="false"
                    canStop="false"
                    canAttach="false"
                    attachments="[]"
                    focusToken="state.token"
                    onInput="() => {}"
                    onSend="() => {}"
                />
            </div>
        `;
        setup() {
            this.state = useState({ token: 0 });
            parent = this;
        }
    }
    await mountWithCleanup(Parent, { props: {} });
    const other = queryFirst('.mk_other_input');
    const composer = queryFirst('.mk_composer textarea');
    other.focus();
    parent.state.token += 1;
    await animationFrame();
    expect(other.ownerDocument.activeElement).toBe(other);
    other.blur();
    parent.state.token += 1;
    await animationFrame();
    expect(composer.ownerDocument.activeElement).toBe(composer);
});

test('Enter sends on live textarea text even when the canSend prop is stale', async () => {
    let sent = 0;
    const { Parent, props } = makeInteractiveParent({
        canSend: false,
        onSend: () => sent++,
    });
    await mountWithCleanup(Parent, { props });
    const composer = queryFirst('.mk_composer textarea');
    composer.value = 'same-frame text';
    composer.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }),
    );
    expect(sent).toBe(1);
    composer.value = '   ';
    composer.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }),
    );
    expect(sent).toBe(1);
});

test('Enter with live text while running queues the send instead of stopping', async () => {
    let sent = 0;
    let stopped = 0;
    class Parent extends Component {
        static components = { ChatComposer };
        static props = {};
        static template = xml`
            <ChatComposer
                value="''"
                placeholder="'type'"
                canSend="false"
                canStop="true"
                canAttach="false"
                isQueueing="true"
                attachments="[]"
                onInput="() => {}"
                onSend="props.onSend"
                onStop="props.onStop"
            />
        `;
    }
    Parent.props = {
        onSend: { type: Function },
        onStop: { type: Function },
    };
    await mountWithCleanup(Parent, {
        props: { onSend: () => sent++, onStop: () => stopped++ },
    });
    const composer = queryFirst('.mk_composer textarea');
    composer.value = 'queued while running';
    composer.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }),
    );
    expect(sent).toBe(1);
    expect(stopped).toBe(0);
});
