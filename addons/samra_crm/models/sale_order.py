# -*- coding: utf-8 -*-
"""Restrict the VIP Instant Discount to customers who are actually VIP.

The program is named 'VIP Instant Discount' and was understood to reward tier
customers, but its only condition was an order minimum of AED 20,000 -- so any
walk-in hitting that figure received 7% off. Core loyalty has no
partner-attribute condition, so the gate has to live in code.

It hooks `_get_program_domain`, which sale_loyalty documents as "the base
domain that all programs have to comply to". Every path that considers a
program runs through it -- automatic point computation, reward listing, and
`_try_apply_program` when someone applies one by hand -- so one narrow
condition covers them all. `_get_trigger_domain` gets the same treatment, so
the program stays gated if it is ever switched from automatic to a code.

The condition only ever subtracts one named program; no other program's
applicability changes.
"""

from odoo import models

VIP_PROGRAM_NAME = 'VIP Instant Discount'
ELIGIBLE_TIERS = ('vip', 'vvip')


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _samra_customer_is_vip(self):
        """True when this order's customer holds a tier the discount is for."""
        return self.partner_id.x_vip_tier in ELIGIBLE_TIERS

    def _get_program_domain(self):
        # super() calls ensure_one(), so self is a single order here.
        domain = super()._get_program_domain()
        if self._samra_customer_is_vip():
            return domain
        return domain + [('name', '!=', VIP_PROGRAM_NAME)]

    def _get_trigger_domain(self):
        domain = super()._get_trigger_domain()
        if self._samra_customer_is_vip():
            return domain
        return domain + [('program_id.name', '!=', VIP_PROGRAM_NAME)]
