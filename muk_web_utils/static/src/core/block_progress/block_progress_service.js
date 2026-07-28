// @odoo-module

import { registry } from "@web/core/registry";

import { BlockUIProgress } from "@muk_web_utils/core/block_progress/block_progress_ui";

const mainComponentRegistry = registry.category("main_components");

export const blockProgressService = {
    start() {
        function block(data) {
            mainComponentRegistry.add(
                "BlockUIProgress",
                {
                    Component: BlockUIProgress,
                    props: {
                        totalSteps: data.totalSteps,
                        progressData: data.progressData,
                    },
                },
                { force: true }
            );
        }
        function unblock() {
            mainComponentRegistry.remove("BlockUIProgress");
        }
        return {
            block,
            unblock,
        };
    },
};

registry.category("services").add("block_progress", blockProgressService);
