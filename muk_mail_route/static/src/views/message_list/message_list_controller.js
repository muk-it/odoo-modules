// @odoo-module

import { useState } from '@odoo/owl';
import { useService } from '@web/core/utils/hooks';
import { makeActiveField } from '@web/model/relational_model/utils';

import { SIZES } from '@web/core/ui/ui_service';

import { Field } from '@web/views/fields/field';
import { ListController } from '@web/views/list/list_controller';
import { AttachmentList } from '@mail/core/common/attachment_list';

/**
 * List controller for the lost mails view: adds attachment, author, body and
 * recipient active fields and drives a side preview pane for the selection.
 */
export class MessageListController extends ListController {
    static template = 'muk_mail_route.MessageListView';
    static components = {
        ...ListController.components,
        Field,
        AttachmentList,
    };
    setup() {
        super.setup();
        this.openRecord = () => {};
        this.ui = useState(useService('ui'));
        this.store = useService('mail.store');
        this.previewState = useState({
            selectedRecord: false,
            messageBody: false,
            attachments: [],
        });
    }
    get modelParams() {
        const params = super.modelParams;
        params.config.activeFields.attachment_ids = makeActiveField();
        params.config.activeFields.attachment_ids.related = {
            fields: {
                name: { name: 'name', type: 'char' },
                mimetype: { name: 'mimetype', type: 'char' },
            },
            activeFields: {
                name: makeActiveField(),
                mimetype: makeActiveField(),
            },
        };
        if (!params.config.activeFields.author_id) {
            params.config.activeFields.author_id = makeActiveField();
        }
        if (!params.config.activeFields.body) {
            params.config.activeFields.body = makeActiveField();
        }
        if (!params.config.activeFields.notified_partner_ids) {
            params.config.activeFields.notified_partner_ids = makeActiveField();
            params.config.activeFields.notified_partner_ids.related = {
                fields: {
                    display_name: {
                        name: 'display_name',
                        type: 'char',
                        readonly: true,
                    },
                },
                activeFields: {
                    display_name: makeActiveField(),
                },
            };
        }
        return params;
    }
    get previewEnabled() {
        return this.ui.size >= SIZES.XXL;
    }
    /**
     * Load the given record into the preview pane.
     * @param {object} record the selected list record
     */
    setSelectedRecord(record) {
        this.previewState.selectedRecord = record;
        this.previewState.messageBody = record.data.body;
        this.previewState.attachments = record.data.attachment_ids.records.map(
            (att) => {
                return this.store.Attachment.insert({
                    id: att.resId,
                    name: att.data.name,
                    mimetype: att.data.mimetype,
                });
            },
        );
    }
}
