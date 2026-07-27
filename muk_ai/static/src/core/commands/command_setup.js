// @odoo-module

import { _t } from '@muk_ai/core/compat/translation';
import { registry } from '@web/core/registry';

registry.category('command_setup').add('?', {
    debounceDelay: 200,
    name: _t('AI'),
    placeholder: _t('Search MuK AI chats and agents…'),
    emptyMessage: _t('No AI chat or agent found.'),
});

registry
    .category('command_categories')
    .add('muk_ai', { namespace: '?', name: _t('MuK AI') }, { sequence: 60 });
