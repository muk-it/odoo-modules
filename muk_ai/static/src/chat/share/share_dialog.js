// @odoo-module

import { Component, onWillStart, useState } from '@odoo/owl';

import { Dialog } from '@web/core/dialog/dialog';
import { _t } from '@web/core/l10n/translation';
import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';
import { Record } from '@web/views/record';
import { Field } from '@web/views/fields/field';

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
        this.user = useService('user');
        this.state = useState({ fieldInfo: null });
        this.record = null;
        // The slot renders against a context derived from this component, so
        // an unbound ``capture`` would write the record onto that derived
        // object and leave ``this.record`` null here.
        this.capture = this.capture.bind(this);
        onWillStart(async () => {
            const FieldComponent = registry
                .category('fields')
                .get('many2many_avatar_user');
            const attrs = { options: {} };
            // Odoo 16 has no field descriptors: the registry holds the
            // component, and the arch parser hands the view what is spelled
            // out here. 17.0 replaced all of it with one descriptor object.
            this.state.fieldInfo = {
                name: 'share_user_ids',
                viewType: 'form',
                context: '{}',
                string: '',
                modifiers: {},
                decorations: {},
                rawAttrs: {},
                options: attrs.options,
                FieldComponent,
                fieldsToFetch: FieldComponent.fieldsToFetch,
                domain: await this.candidateDomain(),
                propsFromAttrs: FieldComponent.extractProps({
                    field: { relation: 'res.users' },
                    attrs,
                }),
            };
        });
    }

    /**
     * Keep the datapoint the ``Record`` slot renders with.
     *
     * Odoo 16's ``Record`` takes no ``onRecordChanged`` hook — that arrived in
     * 17.0 — so the slot is the only place it hands the datapoint out.
     *
     * @param {object} record the record datapoint being rendered
     * @returns {string} nothing, so the caller renders no text
     */
    capture(record) {
        this.record = record;
        return '';
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
            `('groups_id', 'in', [${employees}]), ` +
            `('id', 'not in', [1, ${this.user.userId}])]`
        );
    }

    get title() {
        return _t('Share this chat');
    }

    get activeFields() {
        return { share_user_ids: this.state.fieldInfo };
    }

    /**
     * Describe the record's fields, rather than letting ``Record`` fetch them.
     *
     * Odoo 16 parses every value the read returns against this map, so ``id``
     * has to be in it or the datapoint throws on its own primary key.
     *
     * @returns {object} field descriptions keyed by name
     */
    get fields() {
        return {
            id: { name: 'id', type: 'integer', readonly: true },
            share_user_ids: {
                name: 'share_user_ids',
                type: 'many2many',
                relation: 'res.users',
                string: '',
            },
        };
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
