import { Component, onMounted, onWillUnmount, useState } from '@odoo/owl';

import { _t } from '@web/core/l10n/translation';
import { formatDateTime } from '@web/core/l10n/dates';
import { registry } from '@web/core/registry';
import { useService } from '@web/core/utils/hooks';
import { standardFieldProps } from '@web/views/fields/standard_field_props';

import { formatTimestamp } from '@muk_ai/chat/utils';

const { DateTime } = luxon;

const SECOND = 1000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

export class ScheduleCountdownField extends Component {
    static template = 'muk_ai_schedule.ScheduleCountdownField';
    static props = { ...standardFieldProps };
    setup() {
        this.state = useState({ tick: 0 });
        this.intervalId = null;
        this.busHandler = null;
        this.bus = useService('bus_service');
        onMounted(() => {
            this.intervalId = window.setInterval(() => {
                this.state.tick += 1;
            }, SECOND);
            if (this.props.record.resModel === 'muk_ai.session') {
                this.busHandler = (event) => this._onBusEvent(event);
                this.bus.subscribe('muk_ai.event', this.busHandler);
            }
        });
        onWillUnmount(() => {
            if (this.intervalId !== null) {
                window.clearInterval(this.intervalId);
                this.intervalId = null;
            }
            if (this.busHandler) {
                this.bus.unsubscribe('muk_ai.event', this.busHandler);
                this.busHandler = null;
            }
        });
    }
    get value() {
        const raw = this.props.record.data[this.props.name];
        if (!raw) {
            return null;
        }
        if (raw.isLuxonDateTime) {
            return raw.toLocal();
        }
        try {
            const dt = DateTime.fromISO(String(raw), { zone: 'utc' }).toLocal();
            return dt.isValid ? dt : null;
        } catch (_e) {
            return null;
        }
    }
    get diffMs() {
        const target = this.value;
        if (!target) {
            return null;
        }
        void this.state.tick;
        return target.toMillis() - DateTime.now().toMillis();
    }
    get isEmpty() {
        return this.value === null;
    }
    get isPast() {
        const diff = this.diffMs;
        return diff !== null && diff <= 0;
    }
    get absoluteText() {
        const target = this.value;
        return target ? formatDateTime(target) : '';
    }
    get pastLabel() {
        return _t('(due)');
    }
    get countdownText() {
        const diff = this.diffMs;
        if (diff === null || diff <= 0) {
            return '';
        }
        if (diff < MINUTE) {
            const s = Math.max(1, Math.round(diff / SECOND));
            return _t('%ss', s);
        }
        if (diff < HOUR) {
            const m = Math.floor(diff / MINUTE);
            const s = Math.floor((diff % MINUTE) / SECOND);
            return _t('%sm %ss', m, s);
        }
        if (diff < DAY) {
            const h = Math.floor(diff / HOUR);
            const m = Math.floor((diff % HOUR) / MINUTE);
            return _t('%sh %sm', h, m);
        }
        const d = Math.floor(diff / DAY);
        const h = Math.floor((diff % DAY) / HOUR);
        return _t('%sd %sh', d, h);
    }
    get tooltip() {
        const target = this.value;
        if (!target) {
            return '';
        }
        return formatTimestamp(target.toUTC().toISO());
    }
    _onBusEvent(event) {
        if (!event || event.session_id !== this.props.record.resId) {
            return;
        }
        if (event.type !== 'state') {
            return;
        }
        const payload = event.payload || {};
        if (payload.state === 'running') {
            this.state.tick += 1;
        }
    }
}

export const scheduleCountdownField = {
    component: ScheduleCountdownField,
    displayName: _t('Schedule Countdown'),
    supportedTypes: ['datetime'],
};

registry.category('fields').add('schedule_countdown', scheduleCountdownField);
