/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanController } from "@web/views/kanban/kanban_controller";

/**
 * Row click on the Upcoming Occasions views opens the Customer 360.
 *
 * The default opens res.partner's form, which is the record behind the row
 * but not the thing anyone wants at that moment. Someone who clicked a
 * birthday three days out is about to pick up the phone, and what they need
 * is the dossier -- what this customer buys, what they have wishlisted, what
 * was said last -- not an address card with a Sales tab.
 *
 * Overriding openRecord rather than adding a button keeps the gesture the one
 * people already have: click the row.
 */
function openProfile(action, record) {
    action.doAction({
        type: "ir.actions.client",
        tag: "samra_customer_360",
        name: "Customer 360",
        params: { partner_id: record.resId },
    });
}

export class SamraOccasionListController extends ListController {
    setup() {
        super.setup();
        this.actionService = useService("action");
    }

    async openRecord(record) {
        openProfile(this.actionService, record);
    }
}

export class SamraOccasionKanbanController extends KanbanController {
    setup() {
        super.setup();
        this.actionService = useService("action");
    }

    async openRecord(record) {
        openProfile(this.actionService, record);
    }
}

registry.category("views").add("samra_occasion_list", {
    ...listView,
    Controller: SamraOccasionListController,
});

registry.category("views").add("samra_occasion_kanban", {
    ...kanbanView,
    Controller: SamraOccasionKanbanController,
});
