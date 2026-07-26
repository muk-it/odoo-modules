import { describe, expect, test } from '@odoo/hoot';
import { session } from '@web/session';
import { patchWithCleanup } from '@web/../tests/web_test_helpers';

import { getAutoLoadInterval } from '@muk_web_refresh/core/utils';

describe.current.tags('muk_web_refresh');

test('the session value is used when present', async () => {
    patchWithCleanup(session, { pager_autoload_interval: 5000 });
    expect(getAutoLoadInterval()).toBe(5000);
});

test('a missing session value falls back to thirty seconds', async () => {
    patchWithCleanup(session, { pager_autoload_interval: undefined });
    expect(getAutoLoadInterval()).toBe(30000);
});

test('an explicit zero is kept instead of falling back', async () => {
    patchWithCleanup(session, { pager_autoload_interval: 0 });
    expect(getAutoLoadInterval()).toBe(0);
});
