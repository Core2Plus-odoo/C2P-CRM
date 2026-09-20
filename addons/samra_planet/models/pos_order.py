# -*- coding: utf-8 -*-
"""The same automatic issuance, at the till.

pos.order has no relationship to sale.order -- a POS sale never creates one
-- so this issues directly against the POS order rather than trying to find
a sale order that does not exist. Every field the provider's _subject() reads
(name, partner_id, amount_total, amount_tax, currency_id) exists on pos.order
just as it does on sale.order, so the same provider code serves both.
"""

from odoo import api, models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model
    def _process_order(self, order, existing_order):
        order_id = super()._process_order(order, existing_order)
        pos_order = self.browse(order_id)
        if pos_order.partner_id.x_planet_is_tourist:
            pos_order._samra_planet_issue()
        return order_id

    def _samra_planet_issue(self):
        self.ensure_one()
        provider = self.env['samra.planet.provider']._active_provider()
        if not provider:
            return False
        outcome = provider.issue(self)
        return self.env['samra.planet.issuance']._record(self, provider, outcome)
