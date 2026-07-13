import {
    contains,
    defineMailModels,
    openDiscuss,
    start,
    startServer,
} from '@mail/../tests/mail_test_helpers';

import { describe, test } from '@odoo/hoot';

import '@muk_web_chatter/core/thread/thread';

describe.current.tags('desktop');
defineMailModels();

test.tags('muk_web_chatter');
test('squash aligns prevMsg with filtered displayMessages', async () => {
    const pyEnv = await startServer();
    const [aliceId, bobId, carolId] = pyEnv['res.partner'].create([
        { name: 'Alice' },
        { name: 'Bob' },
        { name: 'Carol' },
    ]);
    const channelId = pyEnv['discuss.channel'].create({
        name: 'general',
        channel_type: 'channel',
    });
    pyEnv['mail.message'].create([
        {
            author_id: aliceId,
            body: 'not empty',
            date: '2019-04-20 10:00:00',
            message_type: 'comment',
            model: 'discuss.channel',
            res_id: channelId,
        },
        {
            author_id: bobId,
            body: '',
            date: '2019-04-20 10:01:00',
            message_type: 'comment',
            model: 'discuss.channel',
            res_id: channelId,
        },
        {
            author_id: carolId,
            body: 'not empty',
            date: '2019-04-20 10:02:00',
            message_type: 'comment',
            model: 'discuss.channel',
            res_id: channelId,
        },
        {
            author_id: carolId,
            body: 'not empty',
            date: '2019-04-20 10:03:00',
            message_type: 'comment',
            model: 'discuss.channel',
            res_id: channelId,
        },
    ]);
    await start();
    await openDiscuss(channelId);
    await contains('.o-mail-Message', { count: 3 });
    await contains('.o-mail-Message-header', { count: 2 });
});
