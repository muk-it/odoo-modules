import { Component, onWillStart, useState } from '@odoo/owl';

import { Dialog } from '@web/core/dialog/dialog';
import { _t } from '@web/core/l10n/translation';
import { user } from '@web/core/user';
import { useService } from '@web/core/utils/hooks';
import { Record } from '@web/model/record';
import { Field, getFieldFromRegistry } from '@web/views/fields/field';

/**
 * Pick who may read a chat.
 *
 * The picker is the ordinary form-view field, so it behaves the way it does
 * everywhere else. Reading is the only level there is, so the dialog states
 * it rather than offering it, and what is picked is held until it is saved.
 */
export class AIShareDialog extends Component {
    static template = 'muk_ai.ShareDialog';
    static components = { Dialog, Record, Field };
    static props = {
        sessionId: { type: Number },
        close: { type: Function },
        onChanged: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService('orm');
        this.state = useState({ fieldInfo: null, dirty: false });
        this.record = null;
        this.hooks = {
            onRecordChanged: (record) => {
                this.record = record;
                this.state.dirty = true;
            },
        };
        onWillStart(async () => {
            this.state.fieldInfo = {
                name: 'share_user_ids',
                field: getFieldFromRegistry('many2many', 'many2many_avatar_user'),
                attrs: {},
                options: {},
                string: '',
                limit: 80,
                domain: await this.candidateDomain(),
                related: {
                    fields: { display_name: { name: 'display_name', type: 'char' } },
                    activeFields: {
                        display_name: {
                            attrs: {},
                            options: {},
                            domain: '[]',
                            string: '',
                        },
                    },
                },
            };
        });
    }

    /**
     * Offer the colleagues a chat can usefully be shared with.
     *
     * Portal users are left out because a transcript is internal, the owner —
     * who is whoever opened this dialog, since nobody else is offered it —
     * because the chat is already theirs, and anybody outside the employee
     * group because they could not open it anyway.
     */
    async candidateDomain() {
        const [, employees] = await this.orm.call(
            'ir.model.data',
            'check_object_reference',
            ['base', 'group_user'],
        );
        return (
            `[('share', '=', False), ('active', '=', True), ` +
            `('group_ids', 'in', [${employees}]), ` +
            `('id', 'not in', [1, ${user.userId}])]`
        );
    }

    get title() {
        return _t('Share this chat');
    }

    get activeFields() {
        return { share_user_ids: this.state.fieldInfo };
    }

    async save() {
        const list = this.record?.data?.share_user_ids;
        if (list) {
            await this.orm.write('muk_ai.session', [this.props.sessionId], {
                share_user_ids: [[6, 0, list.records.map((record) => record.resId)]],
            });
            this.props.onChanged?.();
        }
        this.props.close();
    }
}
