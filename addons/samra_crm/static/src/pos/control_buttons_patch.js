/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { SamraClientDialog } from "./samra_client_dialog";

patch(ControlButtons.prototype, {
    openSamraClient() {
        const partner = this.partner;
        if (!partner) {
            // The button sits beside Pricelist and Refund, which are equally
            // meaningless without a customer; say so rather than opening an
            // empty panel.
            this.notification.add(
                _t("Select a customer first, then open Client 360."),
                { type: "warning" }
            );
            return;
        }
        this.dialog.add(SamraClientDialog, { partnerId: partner.id });
    },
});
