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
            preset: "12m",
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

    /**
     * Dates are formatted from local parts rather than toISOString(), which
     * converts to UTC first and can hand back yesterday for anyone east of
     * Greenwich -- including, pointedly, Dubai.
     */
    iso(date) {
        const month = String(date.getMonth() + 1).padStart(2, "0");
        const day = String(date.getDate()).padStart(2, "0");
        return `${date.getFullYear()}-${month}-${day}`;
    }

    today() {
        return this.iso(new Date());
    }

    defaultFrom() {
        const date = new Date();
        date.setMonth(date.getMonth() - 12);
        return this.iso(date);
    }

    get presets() {
        return [
            { key: "mtd", label: "This Month" },
            { key: "last_month", label: "Last Month" },
            { key: "qtd", label: "This Quarter" },
            { key: "last_quarter", label: "Last Quarter" },
            { key: "ytd", label: "Year to Date" },
            { key: "12m", label: "Last 12 Months" },
        ];
    }

    /** Period boundaries for a preset key, as local dates. */
    presetRange(key) {
        const now = new Date();
        const year = now.getFullYear();
        const month = now.getMonth();
        const quarterStart = month - (month % 3);

        switch (key) {
            case "mtd":
                return [new Date(year, month, 1), now];
            case "last_month":
                // Day 0 of a month is the last day of the one before it.
                return [new Date(year, month - 1, 1), new Date(year, month, 0)];
            case "qtd":
                return [new Date(year, quarterStart, 1), now];
            case "last_quarter":
                return [new Date(year, quarterStart - 3, 1), new Date(year, quarterStart, 0)];
            case "ytd":
                return [new Date(year, 0, 1), now];
            default: {
                const from = new Date();
                from.setMonth(from.getMonth() - 12);
                return [from, now];
            }
        }
    }

    async applyPreset(key) {
        const [from, to] = this.presetRange(key);
        this.state.filters.date_from = this.iso(from);
        this.state.filters.date_to = this.iso(to);
        this.state.preset = key;
        await this.load();
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
        if (field === "date_from" || field === "date_to") {
            // Typing a date puts the range outside any preset, so no chip
            // should keep claiming to describe it.
            this.state.preset = null;
        }
        this.load();
    }

    resetFilters() {
        this.state.filters.warehouse_id = "";
        this.state.filters.user_id = "";
        this.applyPreset("12m");
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

    formatDate(value) {
        if (!value) {
            return "—";
        }
        const parsed = new Date(value.replace(" ", "T"));
        if (Number.isNaN(parsed.getTime())) {
            return value;
        }
        return parsed.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
    }

    /** "Today" / "Tomorrow" / "in 9 days" -- a countdown, not a date.
     *  Somebody scanning this panel is deciding what to do this morning, and
     *  a date makes them do the subtraction themselves. */
    occasionWhen(row) {
        const days = Number(row.days_away || 0);
        if (days <= 0) {
            return "Today";
        }
        if (days === 1) {
            return "Tomorrow";
        }
        return `in ${days} days`;
    }

    /** Urgency class for the countdown chip. */
    occasionUrgency(row) {
        const days = Number(row.days_away || 0);
        if (days <= 1) {
            return "samra-chip samra-chip--due";
        }
        if (days <= 7) {
            return "samra-chip samra-chip--soon";
        }
        return "samra-chip";
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

    drillOccasions(domain, name) {
        this.drill("occasions", domain, name || "Upcoming Occasions");
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
