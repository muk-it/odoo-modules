import { usePlugin } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { user } from '@web/core/user';

import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';

registry.category('command_setup').add('#', {
    debounceDelay: 200,
    name: _t('AI'),
    placeholder: _t('Search MuK AI chats...'),
});

registry
    .category('command_categories')
    .add('muk_ai', { namespace: '#', name: _t('MuK AI') }, { sequence: 60 });

registry.category('command_provider').add('muk_ai_sessions', {
    namespace: '#',
    async provide({ searchValue = '' }) {
        const chat = usePlugin(AIChatPlugin);
        const needle = searchValue.trim();
        const sessions = await chat.orm.searchRead(
            'muk_ai.session',
            [
                ['user_id', '=', user.userId],
                ...(needle ? [['name', 'ilike', needle]] : []),
            ],
            ['id', 'name'],
            { limit: 20, order: 'create_date DESC' },
        );
        return [
            {
                name: _t('New Chat'),
                category: 'muk_ai',
                async action() {
                    const values = needle ? { name: needle } : {};
                    chat.openFullChat(await chat.createSession(values));
                },
            },
            ...sessions.map((session) => ({
                name: session.name || _t('Chat %s', session.id),
                category: 'muk_ai',
                action: () => chat.openFullChat(session.id),
            })),
        ];
    },
});
