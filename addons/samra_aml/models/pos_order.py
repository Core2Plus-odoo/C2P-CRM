# -*- coding: utf-8 -*-
"""The control at the till.

Enforced server-side, in _process_order, which is where the POS frontend hands
an order over to be created. That placement is deliberate: a check written
only in the POS JavaScript is a hint, because the frontend is a separate
application that can be stale, offline or simply out of date after an upgrade.
Server-side, the order cannot be created at all.

The cost is that the cashier learns at validation rather than when they attach
the customer. A frontend warning belongs on top of this -- not instead of it.
"""

from odoo import api, models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model
    def _process_order(self, order, existing_order):
        partner_id = (order or {}).get('partner_id')
        if partner_id:
            partner = self.env['res.partner'].browse(partner_id)
            if partner.exists():
                partner._samra_aml_assert_sellable(
                    document=(order or {}).get('name'))
        return super()._process_order(order, existing_order)
