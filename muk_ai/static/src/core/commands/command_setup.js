import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';

registry.category('command_setup').add('#', {
    debounceDelay: 200,
    name: _t('AI'),
    placeholder: _t('Search MuK AI chats and agents…'),
    emptyMessage: _t('No AI chat or agent found.'),
});

registry.category('command_categories').add(
    'muk_ai',
    { namespace: '#', name: _t('MuK AI') },
    { sequence: 60 },
);
