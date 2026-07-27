// @odoo-module

import { onWillUpdateProps, useComponent } from '@odoo/owl';

/**
 * Run a callback with the current record now and whenever it changes.
 *
 * Stands in for ``useRecordObserver``, which only exists from 17.0 on.
 *
 * @param {(record: object) => void} callback invoked with the field's record
 */
export function useRecordObserver(callback) {
    const component = useComponent();
    callback(component.props.record);
    onWillUpdateProps((nextProps) => callback(nextProps.record));
}
