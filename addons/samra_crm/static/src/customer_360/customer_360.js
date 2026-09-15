/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Customer 360 — the clienteling profile.
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
                open: false,
                query: "",
                results: [],
                tray: [],
                searching: false,
                saving: false,
                message: null,
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

    money(value, decimals = 0) {
        const amount = Number(value || 0);
        return `${this.currency} ${amount.toLocaleString("en-AE", {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
        })}`;
    }

    /** Whole points, formatted. Math is a global, so it cannot live in the template. */
    points(value) {
        return Math.round(Number(value) || 0).toLocaleString("en-AE");
    }

    get affordableRewards() {
        const rewards = this.state.data?.loyalty?.rewards || [];
        return rewards.filter((reward) => reward.affordable).length;
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

    // --- showing-room capture ---------------------------------------

    get capture() {
        return this.state.capture;
    }

    openCapture() {
        const capture = this.state.capture;
        capture.open = true;
        capture.message = null;
        this.runSearch("");
    }

    closeCapture() {
        const capture = this.state.capture;
        capture.open = false;
        capture.query = "";
        capture.results = [];
        capture.tray = [];
        capture.message = null;
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

            // Reload so Viewed Products and Wishlist reflect what just happened.
            this.state.data = await this.orm.call(
                "res.partner", "get_samra_profile", [[this.partnerId]]
            );
        } catch (error) {
            capture.message = error.message?.data?.message || "Could not save. Nothing was logged.";
        }
        capture.saving = false;
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
        this.openRecords("x_samra_wishlist",
            [["x_partner_id", "=", this.partnerId]], "Wishlist");
    }

    openViewed() {
        this.openRecords("x_samra_viewed_product",
            [["x_partner_id", "=", this.partnerId]], "Viewed Products");
    }

    openWhatsapp() {
        this.openRecords("x_samra_whatsapp_log",
            [["x_partner_id", "=", this.partnerId]], "WhatsApp Log");
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
}

registry.category("actions").add("samra_customer_360", SamraCustomer360);
