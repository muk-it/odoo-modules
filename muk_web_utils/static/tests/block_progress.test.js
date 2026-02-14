import { expect, test } from "@odoo/hoot";
import { registry } from "@web/core/registry";

test.tags("muk_web_utils");
test("block progress service registers and removes main component", async () => {
    const service = registry.category("services").get("block_progress");
    const instance = service.start();
    const mainComponents = registry.category("main_components");
    instance.block({ totalSteps: 2, progressData: { step: 0, value: 0 } });
    expect(mainComponents.contains("BlockUIProgress")).toBe(true);
    instance.unblock();
    expect(mainComponents.contains("BlockUIProgress")).toBe(false);
});
