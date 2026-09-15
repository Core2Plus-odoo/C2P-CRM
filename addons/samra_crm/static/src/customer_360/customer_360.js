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
        this.state = useState({ loading: true, error: null, data: null });

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
        const number = this.state.data?.mobile || this.state.data?.phone;
        return number ? `tel:${number.replace(/\s+/g, "")}` : null;
    }

    get whatsappHref() {
        const number = this.state.data?.mobile || this.state.data?.phone;
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
