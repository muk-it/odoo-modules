import { describe, expect, test } from '@odoo/hoot';
import { Component, useState, xml } from '@odoo/owl';
import { animationFrame } from '@odoo/hoot-mock';
import { mockService, mountWithCleanup } from '@web/../tests/web_test_helpers';
import { defineMailModels } from '@mail/../tests/mail_test_helpers';

import {
    sessionChannel,
    useSessionChannel,
} from '@muk_ai/chat/session/session_channel';
import { isChatOpen, useOpenSession } from '@muk_ai/chat/session/open_sessions';

describe.current.tags('muk_ai');
defineMailModels();

function mockBus() {
    const channels = [];
    mockService('bus_service', {
        addChannel: (channel) => channels.push(channel),
        deleteChannel: (channel) => {
            const index = channels.indexOf(channel);
            if (index >= 0) {
                channels.splice(index, 1);
            }
        },
        subscribe() {},
        unsubscribe() {},
        start() {},
    });
    return channels;
}

function makeFollower() {
    class Follower extends Component {
        static props = ['*'];
        static template = xml`<div/>`;
        setup() {
            this.state = useState({ sessionId: this.props.sessionId ?? null });
            useSessionChannel(() => this.state.sessionId);
            useOpenSession(() => this.state.sessionId);
        }
    }
    return Follower;
}

test('sessionChannel names the session record channel', () => {
    expect(sessionChannel(42)).toBe('muk_ai.session_42');
});

test('a surface follows the channel of the session it shows', async () => {
    const channels = mockBus();
    await mountWithCleanup(makeFollower(), { props: { sessionId: 7 } });
    expect(channels).toEqual([sessionChannel(7)]);
    expect(isChatOpen(7)).toBe(true);
});

test('no session means no subscription', async () => {
    const channels = mockBus();
    await mountWithCleanup(makeFollower(), { props: { sessionId: null } });
    expect(channels).toEqual([]);
});

test('switching session swaps the channel', async () => {
    const channels = mockBus();
    const surface = await mountWithCleanup(makeFollower(), {
        props: { sessionId: 7 },
    });
    surface.state.sessionId = 9;
    await animationFrame();
    expect(channels).toEqual([sessionChannel(9)]);
    expect(isChatOpen(7)).toBe(false);
    expect(isChatOpen(9)).toBe(true);
});

test('two surfaces on one session keep it while either remains', async () => {
    const channels = mockBus();
    const Follower = makeFollower();
    const first = await mountWithCleanup(Follower, { props: { sessionId: 7 } });
    await mountWithCleanup(Follower, { props: { sessionId: 7 } });
    expect(channels).toEqual([sessionChannel(7)]);
    first.__owl__.destroy();
    await animationFrame();
    expect(channels).toEqual([sessionChannel(7)]);
    expect(isChatOpen(7)).toBe(true);
});

test('a reader follows the chat but never answers its client actions', async () => {
    mockBus();
    class Reader extends Component {
        static props = ['*'];
        static template = xml`<div/>`;
        setup() {
            this.state = useState({ sessionId: 31, readonly: true });
            useSessionChannel(() => this.state.sessionId);
            useOpenSession(() => (this.state.readonly ? null : this.state.sessionId));
        }
    }
    const reader = await mountWithCleanup(Reader, {});
    expect(isChatOpen(31)).toBe(false);
    reader.state.readonly = false;
    await animationFrame();
    expect(isChatOpen(31)).toBe(true);
});
