import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';

// On Odoo 18 the mail/discuss command palette already owns the "#" namespace
// (channels); on 19 it does not. Import it first so that — when present — it
// registers "#" before us, then only define "#" when it is still free. This
// lets MuK AI share the namespace without either side clobbering the other.
import '@mail/discuss/core/web/command_palette';

const commandSetup = registry.category('command_setup');
if (!commandSetup.contains('#')) {
    commandSetup.add('#', {
        debounceDelay: 200,
        name: _t('AI'),
        placeholder: _t('Search MuK AI chats and agents…'),
        emptyMessage: _t('No AI chat or agent found.'),
    });
}

registry.category('command_categories').add(
    'muk_ai',
    { namespace: '#', name: _t('MuK AI') },
    { sequence: 60 },
);
