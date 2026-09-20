# -*- coding: utf-8 -*-
"""The control on the back-office side of the counter."""

from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        # Before, not after: a confirmed order reserves stock and can be
        # invoiced, and unwinding that is worse than refusing it.
        for order in self:
            order.partner_id._samra_aml_assert_sellable(document=order.name)
        return super().action_confirm()
