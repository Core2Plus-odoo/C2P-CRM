/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Dashboard drill-down.
 *
 * A dashboard figure used to hand its domain to act_window, which dropped the
 * user into Odoo's generic order list -- correct records, wrong register. The
 * numbers were presented as an instrument panel and then explained by a grid
 * of technical columns.
 *
 * This screen answers the same question in the same voice: the total restated,
 * how it splits, then the records. Rows come pre-formatted from the server,
 * because a presentation surface should not have to know that a branch lives
 * on warehouse_id.
 */
export class SamraBreakdown extends Component {
    static template = "samra_crm.Breakdown";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ loading: true, error: null, data: null });

        const params = this.props.action.params || {};
        this.kind = params.kind || "orders";
        this.domain = params.domain || [];
        this.title = params.title || "Breakdown";

        onWillStart(async () => {
            try {
                this.state.data = await this.orm.call(
                    "samra.dashboard", "get_breakdown",
                    [this.kind, this.domain, this.title]
                );
            } catch (error) {
                this.state.error = error.message?.data?.message || "Could not load the breakdown.";
            }
            this.state.loading = false;
        });
    }

    get currency() {
        return this.state.data?.currency || "AED";
    }

    money(value) {
        return `${this.currency} ${Number(value || 0).toLocaleString("en-AE", {
            maximumFractionDigits: 0,
        })}`;
    }

    plain(value) {
        return Number(value || 0).toLocaleString("en-AE", { maximumFractionDigits: 0 });
    }

    summaryValue(item) {
        return item.money ? this.money(item.value) : this.plain(item.value);
    }

    /** Numbers right-align and use tabular figures; text does not. */
    isNumeric(index) {
        return index >= (this.state.data?.numeric_from ?? 99);
    }

    cell(row, index) {
        const value = row.cells[index];
        if (this.isNumeric(index) && typeof value === "number") {
            // The last numeric column is the money one in every kind.
            return index === row.cells.length - 1 ? this.money(value) : this.plain(value);
        }
        return value;
    }

    backToDashboard() {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "samra_management_dashboard",
            name: "Management Dashboard",
        });
    }

    /**
     * A row leads to the customer's dossier, not to a form view. Someone who
     * drilled into revenue wants to know who, and the dossier is the answer.
     */
    openRow(row) {
        if (row.partner_id) {
            this.action.doAction({
                type: "ir.actions.client",
                tag: "samra_customer_360",
                name: "Customer 360",
                params: { partner_id: row.partner_id },
            });
        }
    }
}

registry.category("actions").add("samra_management_breakdown", SamraBreakdown);
