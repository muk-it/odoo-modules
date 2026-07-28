// @odoo-module

import { Component, useEffect, useState } from "@odoo/owl";

export class BlockUIProgress extends Component {
    static template = "BlockUIProgress";
    static props = {
        progressData: { type: Object },
        totalSteps: { type: Number },
    };
    setup() {
        this.timer = undefined;
        this.timeStart = Date.now();
        this.state = useState({
            timeLeft: null,
        });
        useEffect(
            () => {
                this.updateTimer();
                return () => {
                    clearInterval(this.timer);
                };
            },
            () => []
        );
    }
    get minutesLeft() {
        return this.state.timeLeft.toFixed(2);
    }
    get secondsLeft() {
        return Math.round(this.state.timeLeft * 60);
    }
    updateTimer() {
        if (this.timer) {
            clearInterval(this.timer);
        }
        const elapsedTime = Date.now() - this.timeStart;
        const progress = this.props.progressData.value || 1;
        const remainingRatio = (100 - progress) / progress;
        this.state.timeLeft = (elapsedTime * remainingRatio) / 60000;
        this.timer = setInterval(() => this.updateTimer(), 1000);
    }
}
