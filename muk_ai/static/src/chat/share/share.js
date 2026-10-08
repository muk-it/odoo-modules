import { Component, onWillStart, proxy, t, useProps, usePlugin } from '@odoo/owl';

import { Dialog } from '@web/core/dialog/dialog';
import { _t } from '@web/core/l10n/translation';
import { AvatarTag } from '@web/core/tags_list/avatar_tag';
import { user } from '@web/core/user';
import { Many2XAutocomplete } from '@web/views/fields/relational_utils';

import { AIChatPlugin } from '@muk_ai/core/chat_plugin/chat_plugin';
import { avatarUrl } from '@muk_ai/core/utils/utils';

/**
 * Pick the colleagues who may read a chat. Reading is the only level there
 * is, so the dialog states it, and nothing changes until it is saved.
 */
class ShareDialog extends Component {
    static template = 'muk_ai.ShareDialog';
    static components = { AvatarTag, Dialog, Many2XAutocomplete };
    props = useProps({ close: t.function(), session: t.object() });
    chat = usePlugin(AIChatPlugin);
    state = proxy({ users: [] });
    avatarUrl = avatarUrl;
    setup() {
        onWillStart(async () => {
            const ids = this.props.session.data.share_user_ids;
            this.state.users = ids.length
                ? await this.chat.orm.read('res.users', ids, ['display_name'])
                : [];
        });
    }
    get ids() {
        return this.state.users.map((record) => record.id);
    }
    get dirty() {
        const before = this.props.session.data.share_user_ids;
        return (
            before.length !== this.ids.length ||
            this.ids.some((id) => !before.includes(id))
        );
    }
    get picker() {
        return {
            resModel: 'res.users',
            fieldString: _t('Readers'),
            placeholder: _t('Add a colleague...'),
            activeActions: { create: false, createEdit: false },
            getDomain: () => [
                ['share', '=', false],
                ['active', '=', true],
                ['id', 'not in', [user.userId, ...this.ids]],
            ],
            update: (records) => {
                const added = (records || []).filter(
                    (record) => !this.ids.includes(record.id),
                );
                this.state.users = [...this.state.users, ...added];
            },
        };
    }
    async save() {
        if (!this.dirty) {
            return;
        }
        const { session } = this.props;
        await this.chat.orm.write('muk_ai.session', [session.id], {
            share_user_ids: [[6, 0, this.ids]],
        });
        session.data.share_user_ids = this.ids;
        if (this.chat.rows[session.id]) {
            this.chat.rows[session.id].share_user_ids = this.ids;
        }
        this.props.close();
    }
}

/** Who may read a chat, stated above the composer, with the way to change it. */
export class ShareBar extends Component {
    static template = 'muk_ai.ShareBar';
    props = useProps({ session: t.object() });
    chat = usePlugin(AIChatPlugin);
    avatarUrl = avatarUrl;
    get summary() {
        const count = this.props.session.data.share_user_ids.length;
        if (!count) {
            return this.props.session.readonly ? '' : _t('Only you can read this chat');
        }
        return count === 1
            ? _t('1 person can read this chat')
            : _t('%s people can read this chat', count);
    }
    open() {
        this.chat.dialog.add(ShareDialog, { session: this.props.session });
    }
}
