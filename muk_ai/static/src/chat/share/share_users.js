import { Component } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { useService } from '@web/core/utils/hooks';

import { AIShareDialog } from '@muk_ai/chat/share/share_dialog';

/**
 * Who a chat is shared with, stated above the composer.
 *
 * A sentence and some faces, nothing more: the picker lives in a dialog, so
 * opening it never changes the height of anything around the transcript.
 */
export class AIChatShareUsers extends Component {
    static template = 'muk_ai.ChatShareUsers';
    static props = {
        sessionId: { type: Number },
        readonly: { type: Boolean, optional: true },
        shareIds: { type: Array, optional: true },
        onChanged: { type: Function, optional: true },
    };

    setup() {
        this.dialog = useService('dialog');
    }

    get canShare() {
        return !this.props.readonly;
    }

    get shareIds() {
        return this.props.shareIds || [];
    }

    get summary() {
        const count = this.shareIds.length;
        if (!count) {
            return this.canShare ? _t('Only you can read this chat') : '';
        }
        return count === 1
            ? _t('1 person can read this chat')
            : _t('%s people can read this chat', count);
    }

    avatar(userId) {
        return `/web/image/res.users/${userId}/avatar_128`;
    }

    openDialog() {
        this.dialog.add(AIShareDialog, {
            sessionId: this.props.sessionId,
            onChanged: () => this.props.onChanged?.(),
        });
    }
}
