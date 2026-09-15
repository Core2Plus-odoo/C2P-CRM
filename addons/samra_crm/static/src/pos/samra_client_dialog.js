/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";

/**
 * Client 360 for the till.
 *
 * Deliberately not the backend dossier. The point of sale runs its own
 * frontend from point_of_sale._assets_pos, with a trimmed core that carries no
 * backend action service -- so there is nothing to drill down into, and a
 * screen built around drill-down would be mostly dead ends. What survives the
 * move is the part an associate needs mid-sale: who this is, what they like,
 * what they nearly bought, and what they have already spent.
 *
 * The call goes through pos.data, which is the POS's own wrapper over the ORM.
 * A till keeps selling when the network drops, so a failure here says so
 * plainly rather than leaving a spinner in front of a customer.
 */
export class SamraClientDialog extends Component {
    static template = "samra_crm.SamraClientDialog";
    static components = { Dialog };
    static props = {
        partnerId: { type: Number },
        close: { type: Function },
    };

    setup() {
        this.pos = usePos();
        this.state = useState({ loading: true, error: null, data: null });

        onWillStart(async () => {
            try {
                const result = await this.pos.data.call(
                    "res.partner", "get_samra_profile", [[this.props.partnerId]]
                );
                this.state.data = result;
            } catch {
                this.state.error =
                    "Could not reach the server. Client details need a connection — " +
                    "the sale itself is unaffected.";
            }
            this.state.loading = false;
        });
    }

    get currency() {
        return this.state.data?.currency || "AED";
    }

    get analytics() {
        return this.state.data?.analytics || {};
    }

    money(value) {
        return `${this.currency} ${Number(value || 0).toLocaleString("en-AE", {
            maximumFractionDigits: 0,
        })}`;
    }

    points(value) {
        return Math.round(Number(value) || 0).toLocaleString("en-AE");
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

    /** Preferences as label/value pairs, skipping the blanks. */
    get preferences() {
        const prefs = this.state.data?.preferences || {};
        return [
            ["Gold", prefs.gold_colour],
            ["Category", prefs.category],
            ["Collection", prefs.collection],
            ["Size", prefs.size],
            ["Diamond", prefs.diamond_spec],
            ["Gemstone", prefs.gemstone],
            ["Style", prefs.style],
            ["Budget", prefs.budget ? this.money(prefs.budget) : ""],
        ]
            .filter((pair) => pair[1])
            .map((pair) => ({ label: pair[0], value: pair[1] }));
    }

    /** Three purchases is what fits without scrolling on a till screen. */
    get recentOrders() {
        return (this.state.data?.orders || []).slice(0, 3);
    }

    get wishlist() {
        return (this.state.data?.wishlist || []).slice(0, 6);
    }

    /**
     * Recommendations, four of them, each marked with whether this till can
     * actually sell it.
     *
     * The POS only loads products its configuration makes available, and the
     * engine recommends from the whole catalogue -- it has no idea which
     * branch the associate is standing in. A suggestion for a piece that
     * cannot be rung up is still worth showing, because the associate can go
     * and fetch it or order it in, but it must not look tappable.
     */
    get recommendations() {
        const rows = this.state.data?.recommendations?.products || [];
        return rows.slice(0, 4).map((rec) => ({
            ...rec,
            product: this.pos.models["product.product"].get(rec.id),
        }));
    }

    /**
     * Tap a suggestion, it joins the sale.
     *
     * At the till the useful gesture is not "tell me more", it is "add it".
     * The associate is standing with the customer and the piece in front of
     * them; the alternative is searching the catalogue for something the
     * screen already named.
     */
    async addRecommendation(rec) {
        if (!rec.product) {
            return;
        }
        await this.pos.addLineToCurrentOrder(
            { product_id: rec.product, product_tmpl_id: rec.product.product_tmpl_id },
            {}
        );
        // Close so the line is visible. Staying open would hide the very
        // thing the tap just did.
        this.props.close();
    }
}
