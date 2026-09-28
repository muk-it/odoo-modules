import { proxy } from '@odoo/owl';
import { useService } from '@web/core/utils/hooks';
import { makeActiveField } from '@web/model/relational_model/utils';

import { SIZES } from '@web/core/ui/ui_utils';

import { Field } from '@web/views/fields/field';
import { ListController } from '@web/views/list/list_controller';
import { groupAttachments } from '@mail/utils/common/attachments';

import { ReadonlyAttachmentList } from '@muk_mail_utils/core/attachment/attachment_list';

/**
 * List controller for the message search view: adds attachment, author, body
 * and recipient active fields and drives a side preview pane for the selection.
 */
export class MessageListController extends ListController {
    static template = 'muk_mail_utils.MessageListView';
    static components = {
        ...ListController.components,
        Field,
        ReadonlyAttachmentList,
    };
    setup() {
        super.setup();
        this.store = useService('mail.store');
        this.previewState = proxy({
            selectedRecord: false,
            messageBody: false,
            attachmentGroups: [],
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
    get className() {
        return `${super.className} mk_message_list_view`;
    }
    get previewEnabled() {
        return this.uiService.size >= SIZES.XXL;
    }
    openRecord() {}
    /**
     * Load the given record into the preview pane.
     * @param {object} record the selected list record
     */
    setSelectedRecord(record) {
        this.previewState.selectedRecord = record;
        this.previewState.messageBody = record.data.body;
        this.previewState.attachmentGroups = groupAttachments(
            record.data.attachment_ids.records.map((attachment) =>
                this.store['ir.attachment'].insert({
                    id: attachment.resId,
                    name: attachment.data.name,
                    mimetype: attachment.data.mimetype,
                }),
            ),
        );
    }
}
