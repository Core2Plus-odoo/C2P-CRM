/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// Trend chart geometry. Fixed viewBox, so the SVG scales with its container
// while the maths below stays in one place rather than scattered through the
// template -- OWL expressions cannot reach Math anyway.
const CHART = {
    width: 760,
    left: 60,
    slot: 115,
    barWidth: 74,
    baseline: 150,
    plotHeight: 100,
    // The order-count line lives in a shallow band above the baseline so it
    // reads as a second series rather than competing with the revenue bars.
    lineBand: 28,
};

const DONUT_RADIUS = 15.9;   // circumference ≈ 100, so a percentage is a length
const DONUT_START = 25;      // rotate the first segment to twelve o'clock
const SEGMENT_TOKENS = [
    "var(--samra-seg-1)", "var(--samra-seg-2)", "var(--samra-seg-3)",
    "var(--samra-seg-4)", "var(--samra-seg-5)",
];

/**
 * Customer 360 — the clienteling dossier.
 *
 * All data arrives from a single `get_samra_profile` call. Every summary
 * element carries the domain that produced it, so drilling down opens the
 * exact record set the number was computed from.
 */
export class SamraCustomer360 extends Component {
    static template = "samra_crm.Customer360";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            error: null,
            data: null,
            // Showing-room capture: a tray an associate fills while presenting,
            // saved once at the end rather than a form filled per item.
            capture: {
                open: false, query: "", results: [], tray: [],
                searching: false, saving: false, message: null,
            },
        });
        this.searchTimer = null;

        const params = this.props.action.params || {};
        this.partnerId = params.partner_id || this.props.action.context?.active_id;

        onWillStart(async () => {
            if (!this.partnerId) {
                this.state.error = "No customer selected.";
                this.state.loading = false;
                return;
            }
            try {
                this.state.data = await this.orm.call(
                    "res.partner", "get_samra_profile", [[this.partnerId]]
                );
            } catch (error) {
                this.state.error = error.message?.data?.message || "Could not load this profile.";
            }
            this.state.loading = false;
        });
    }

    // --- formatting -------------------------------------------------

    get currency() {
        return this.state.data?.currency || "AED";
    }

    get analytics() {
        return this.state.data?.analytics || {};
    }

    money(value, decimals = 0) {
        return `${this.currency} ${this.plain(value, decimals)}`;
    }

    plain(value, decimals = 0) {
        return Number(value || 0).toLocaleString("en-AE", {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
        });
    }

    /** Axis and bar labels need to stay short or they collide. */
    compact(value) {
        const amount = Number(value || 0);
        if (!amount) {
            return "none";
        }
        if (Math.abs(amount) >= 1000) {
            return `${(amount / 1000).toLocaleString("en-AE", { maximumFractionDigits: 1 })}k`;
        }
        return this.plain(amount);
    }

    /**
     * Axis ticks always name a number. compact() renders zero as "none",
     * which reads correctly under an empty bar and absurdly on a scale --
     * an axis of "none / none / 0" describes nothing.
     */
    axisLabel(value) {
        const amount = Number(value || 0);
        if (Math.abs(amount) >= 1000) {
            return `${(amount / 1000).toLocaleString("en-AE", { maximumFractionDigits: 1 })}k`;
        }
        return this.plain(amount);
    }

    points(value) {
        return Math.round(Number(value) || 0).toLocaleString("en-AE");
    }

    percent(value, decimals = 1) {
        return `${Number(value || 0).toFixed(decimals)}%`;
    }

    grams(value) {
        return Number(value || 0).toLocaleString("en-AE", { maximumFractionDigits: 1 });
    }

    /** "Birthday — today" / "Anniversary — in 9 days".
     *  One string rather than three facts: the occasion, when it is and how
     *  soon are one thought, and the header strip has no room for three. */
    occasionSummary(occasion) {
        const labels = { birthday: "Birthday", anniversary: "Anniversary" };
        const label = labels[occasion.type] || "Occasion";
        const days = Number(occasion.days_away || 0);
        if (days <= 0) {
            return `${label} — today`;
        }
        if (days === 1) {
            return `${label} — tomorrow`;
        }
        return `${label} — in ${days} days`;
    }

    formatDate(value) {
        if (!value) {
            return "—";
        }
        const parsed = new Date(value.replace(" ", "T"));
        if (Number.isNaN(parsed.getTime())) {
            return value;
        }
        return parsed.toLocaleDateString("en-GB", {
            day: "2-digit", month: "short", year: "numeric",
        });
    }

    productImage(productId) {
        return `/web/image/product.product/${productId}/image_128`;
    }

    get affordableRewards() {
        const rewards = this.state.data?.loyalty?.rewards || [];
        return rewards.filter((reward) => reward.affordable).length;
    }

    // --- spend trend ------------------------------------------------

    get trendBars() {
        const months = this.analytics.monthly || [];
        const peakRevenue = Math.max(...months.map((m) => m.revenue), 0);
        const peakOrders = Math.max(...months.map((m) => m.orders), 0);

        return months.map((month, index) => {
            const height = peakRevenue ? (month.revenue / peakRevenue) * CHART.plotHeight : 0;
            const x = CHART.left + index * CHART.slot;
            const lineY = CHART.baseline -
                (peakOrders ? (month.orders / peakOrders) * CHART.lineBand : 0);
            return {
                key: month.label,
                label: month.label,
                x,
                // A month with revenue always draws something, so "small" never
                // renders as "none".
                y: CHART.baseline - Math.max(height, month.revenue > 0 ? 2 : 0),
                height: Math.max(height, month.revenue > 0 ? 2 : 0),
                width: CHART.barWidth,
                centre: x + CHART.barWidth / 2,
                valueY: CHART.baseline - height - 7,
                value: this.compact(month.revenue),
                orders: month.orders,
                lineY,
                empty: !month.revenue,
            };
        });
    }

    /** Three gridlines: zero, half, peak — each labelled with a real value. */
    get trendAxis() {
        const months = this.analytics.monthly || [];
        const peak = Math.max(...months.map((m) => m.revenue), 0);
        // baseline is carried as a flag rather than inferred from the label
        // text: the zero line is structural, and a formatter change should not
        // silently restyle it.
        return [
            { y: CHART.baseline, label: "0", baseline: true },
            { y: CHART.baseline - CHART.plotHeight / 2, label: this.axisLabel(peak / 2),
              baseline: false },
            { y: CHART.baseline - CHART.plotHeight, label: this.axisLabel(peak),
              baseline: false },
        ];
    }

    get trendLine() {
        return this.trendBars.map((bar) => `${bar.centre},${bar.lineY}`).join(" ");
    }

    get trendRight() {
        return CHART.width - 10;
    }

    // --- category donut ---------------------------------------------

    get donutSegments() {
        const rows = this.analytics.by_category || [];
        const total = rows.reduce((sum, row) => sum + row.revenue, 0);
        let offset = DONUT_START;

        return rows.map((row, index) => {
            const share = total ? (row.revenue / total) * 100 : 0;
            const segment = {
                key: row.label,
                label: row.label,
                revenue: row.revenue,
                share,
                colour: SEGMENT_TOKENS[index % SEGMENT_TOKENS.length],
                dash: `${share} ${100 - share}`,
                offset,
                radius: DONUT_RADIUS,
            };
            offset -= share;
            return segment;
        });
    }

    get donutTotal() {
        const rows = this.analytics.by_category || [];
        return rows.reduce((sum, row) => sum + row.revenue, 0);
    }

    // --- drill-down -------------------------------------------------

    openRecords(resModel, domain, name, viewMode = "list,form") {
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: resModel,
            domain,
            views: viewMode.split(",").map((mode) => [false, mode]),
            target: "current",
        });
    }

    openRecord(resModel, resId, name) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: resModel,
            res_id: resId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openOrders() {
        this.openRecords(
            "sale.order",
            [["partner_id", "=", this.partnerId], ["state", "not in", ["draft", "cancel"]]],
            "Purchase History"
        );
    }

    openWishlist() {
        this.openRecords("x_samra_wishlist", [["x_partner_id", "=", this.partnerId]], "Wishlist");
    }

    openViewed() {
        this.openRecords("x_samra_viewed_product", [["x_partner_id", "=", this.partnerId]], "Viewed Products");
    }

    openWhatsapp() {
        this.openRecords("x_samra_whatsapp_log", [["x_partner_id", "=", this.partnerId]], "WhatsApp Log");
    }

    openContactForm() {
        this.openRecord("res.partner", this.partnerId, "Customer");
    }

    // --- quick actions ----------------------------------------------

    get telHref() {
        const number = this.state.data?.phone;
        return number ? `tel:${number.replace(/\s+/g, "")}` : null;
    }

    get whatsappHref() {
        // Odoo 19 folded res.partner.mobile into phone; there is one number.
        const number = this.state.data?.phone;
        if (!number) {
            return null;
        }
        return `https://wa.me/${number.replace(/[^\d]/g, "")}`;
    }

    get mailHref() {
        return this.state.data?.email ? `mailto:${this.state.data.email}` : null;
    }

    // --- showing-room capture ---------------------------------------

    get capture() {
        return this.state.capture;
    }

    openCapture() {
        this.state.capture.open = true;
        this.state.capture.message = null;
        this.runSearch("");
    }

    closeCapture() {
        Object.assign(this.state.capture, {
            open: false, query: "", results: [], tray: [], message: null,
        });
    }

    /**
     * One input serves both typing and a barcode scanner: a scanner is just a
     * keyboard that finishes with Enter. Typing debounces; Enter searches at
     * once and, on a single exact hit, drops it straight into the tray so the
     * associate can keep scanning without looking up.
     */
    onCaptureInput(ev) {
        this.state.capture.query = ev.target.value;
        clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(() => this.runSearch(this.state.capture.query), 220);
    }

    async onCaptureKeydown(ev) {
        if (ev.key !== "Enter") {
            return;
        }
        ev.preventDefault();
        clearTimeout(this.searchTimer);

        const query = this.state.capture.query;
        const results = await this.runSearch(query);
        if (results.length === 1 && query) {
            this.addToTray(results[0]);
            this.state.capture.query = "";
            ev.target.value = "";
            this.runSearch("");
        }
    }

    async runSearch(query) {
        const capture = this.state.capture;
        capture.searching = true;
        try {
            capture.results = await this.orm.call(
                "res.partner", "samra_search_products", [[this.partnerId], query]
            );
        } catch {
            capture.results = [];
        }
        capture.searching = false;
        return capture.results;
    }

    inTray(productId) {
        return this.state.capture.tray.some((item) => item.id === productId);
    }

    addToTray(product) {
        if (!this.inTray(product.id)) {
            this.state.capture.tray.push(product);
        }
        this.state.capture.message = null;
    }

    removeFromTray(productId) {
        const capture = this.state.capture;
        capture.tray = capture.tray.filter((item) => item.id !== productId);
    }

    async saveCapture(toWishlist = false) {
        const capture = this.state.capture;
        if (!capture.tray.length || capture.saving) {
            return;
        }
        capture.saving = true;
        try {
            const result = await this.orm.call(
                "res.partner", "samra_log_viewed",
                [[this.partnerId], capture.tray.map((item) => item.id)],
                { to_wishlist: toWishlist }
            );
            const parts = [`${result.viewed} product(s) logged as shown`];
            if (result.wishlisted) {
                parts.push(`${result.wishlisted} added to wishlist`);
            }
            if (result.branch) {
                parts.push(`at ${result.branch}`);
            }
            capture.message = `${parts.join(", ")}.`;
            capture.tray = [];

            // Reload so the viewed, wishlist and engagement panels reflect it.
            this.state.data = await this.orm.call(
                "res.partner", "get_samra_profile", [[this.partnerId]]
            );
        } catch (error) {
            capture.message = error.message?.data?.message || "Could not save. Nothing was logged.";
        }
        capture.saving = false;
    }
}

registry.category("actions").add("samra_customer_360", SamraCustomer360);
