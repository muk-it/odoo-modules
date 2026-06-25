import { Component, useEffect, useState } from '@odoo/owl';

/**
 * Full-screen blocking overlay that shows a live estimate of the time left
 * until a long-running operation completes.
 */
export class BlockUIProgress extends Component {
    static template = 'BlockUIProgress';
    static props = {
        progressData: { type: Object },
        totalSteps: { type: Number },
    };
    setup() {
        this.timeStart = Date.now();
        this.state = useState({
            timeLeft: null,
        });
        useEffect(
            () => {
                this.updateTimer();
                const timer = setInterval(() => this.updateTimer(), 1000);
                return () => {
                    clearInterval(timer);
                };
            },
            () => [],
        );
    }
    get minutesLeft() {
        return this.state.timeLeft.toFixed(2);
    }
    get secondsLeft() {
        return Math.round(this.state.timeLeft * 60);
    }
    /**
     * Recompute the estimated minutes left from the elapsed time and the
     * current progress ratio.
     */
    updateTimer() {
        const elapsedTime = Date.now() - this.timeStart;
        const progress = this.props.progressData.value || 1;
        const remainingRatio = (100 - progress) / progress;
        this.state.timeLeft = (elapsedTime * remainingRatio) / 60000;
    }
}
