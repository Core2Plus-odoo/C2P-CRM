/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Samra management dashboard.
 *
 * Charts are drawn as CSS bars and inline SVG rather than through a charting
 * library. Every mark is a real element, so each one is independently
 * clickable and carries the server-supplied domain that produced it -- which
 * is what makes the drill-down truthful rather than decorative.
 */
export class SamraDashboard extends Component {
    static template = "samra_crm.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = useState({
            loading: true,
            error: null,
            data: null,
            options: { branches: [], salespeople: [] },
            filters: {
                date_from: this.defaultFrom(),
                date_to: this.today(),
                warehouse_id: "",
                user_id: "",
            },
        });

        onWillStart(async () => {
            try {
                this.state.options = await this.orm.call(
                    "samra.dashboard", "get_filter_options", []
                );
            } catch {
                // Filter lists are a convenience; the dashboard still works without them.
            }
            await this.load();
        });
    }

    today() {
        return new Date().toISOString().slice(0, 10);
    }

    defaultFrom() {
        const date = new Date();
        date.setMonth(date.getMonth() - 12);
        return date.toISOString().slice(0, 10);
    }

    async load() {
        this.state.loading = true;
        this.state.error = null;
        try {
            this.state.data = await this.orm.call(
                "samra.dashboard", "get_dashboard_data", [this.cleanFilters()]
            );
        } catch (error) {
            this.state.error = error.message?.data?.message || "Could not load the dashboard.";
        }
        this.state.loading = false;
    }

    cleanFilters() {
        const filters = {};
        for (const [key, value] of Object.entries(this.state.filters)) {
            if (value !== "" && value !== null && value !== undefined) {
                filters[key] = value;
            }
        }
        return filters;
    }

    onFilterChange(field, event) {
        this.state.filters[field] = event.target.value;
        this.load();
    }

    resetFilters() {
        this.state.filters.date_from = this.defaultFrom();
        this.state.filters.date_to = this.today();
        this.state.filters.warehouse_id = "";
        this.state.filters.user_id = "";
        this.load();
    }

    // --- formatting -------------------------------------------------

    get currency() {
        return this.state.data?.currency || "AED";
    }

    money(value, compact = false) {
        const amount = Number(value || 0);
        if (compact && Math.abs(amount) >= 1000) {
            return `${this.currency} ${(amount / 1000).toLocaleString("en-AE", {
                maximumFractionDigits: 1,
            })}k`;
        }
        return `${this.currency} ${amount.toLocaleString("en-AE", {
            maximumFractionDigits: 0,
        })}`;
    }

    /** Whole points, formatted. Math is a global, so it cannot live in the template. */
    points(value) {
        return Math.round(Number(value) || 0).toLocaleString("en-AE");
    }

    /** Compare loosely: option values arrive from the DOM as strings. */
    isSelected(id, filterValue) {
        return String(id) === String(filterValue);
    }

    percent(value) {
        return `${Number(value || 0).toFixed(1)}%`;
    }

    /** Bar width relative to the largest value in the same series. */
    share(value, rows, key = "revenue") {
        const peak = Math.max(...rows.map((row) => Number(row[key] || 0)), 0);
        return peak ? `${(Number(value || 0) / peak) * 100}%` : "0%";
    }

    // --- drill-down -------------------------------------------------

    /**
     * Every figure drills into the Samra breakdown screen rather than an Odoo
     * list. The domain travels with it, so the screen is showing exactly the
     * records the number was computed from -- but presented in the same
     * register as the dashboard, instead of a grid of technical columns.
     */
    drill(kind, domain, title) {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "samra_management_breakdown",
            name: title,
            params: { kind, domain: domain || [], title },
        });
    }

    drillOrders(domain, name) {
        this.drill("orders", domain, name || "Orders");
    }

    drillLeads(domain, name) {
        this.drill("leads", domain, name || "Opportunities");
    }

    drillCustomers(domain, name) {
        this.drill("customers", domain, name || "Customers");
    }

    openCustomerProfile(partnerId) {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "samra_customer_360",
            name: "Customer 360",
            params: { partner_id: partnerId },
        });
    }
}

registry.category("actions").add("samra_management_dashboard", SamraDashboard);
