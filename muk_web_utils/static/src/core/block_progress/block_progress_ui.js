import { Component, signal, t, useEffect, useProps } from '@odoo/owl';

/**
 * Full-screen blocking overlay that shows a live estimate of the time left
 * until a long-running operation completes.
 */
export class BlockUIProgress extends Component {
    static template = 'BlockUIProgress';
    props = useProps({
        progressData: t.object(),
        totalSteps: t.number(),
    });
    elapsed = signal(0);
    setup() {
        const timeStart = Date.now();
        useEffect(() => {
            const timer = setInterval(
                () => this.elapsed.set(Date.now() - timeStart),
                1000,
            );
            return () => clearInterval(timer);
        });
    }
    /**
     * Estimated minutes left, extrapolated from the elapsed time and the
     * current progress ratio.
     * @returns {number}
     */
    get timeLeft() {
        const progress = this.props.progressData.value || 1;
        return (this.elapsed() * (100 - progress)) / progress / 60000;
    }
    get minutesLeft() {
        return this.timeLeft.toFixed(2);
    }
    get secondsLeft() {
        return Math.round(this.timeLeft * 60);
    }
}
