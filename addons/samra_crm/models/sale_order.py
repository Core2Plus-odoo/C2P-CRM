# -*- coding: utf-8 -*-
"""Restrict the VIP Instant Discount to customers who are actually VIP.

The program is named 'VIP Instant Discount' and was understood to reward tier
customers, but its only condition was an order minimum of AED 20,000 -- so any
walk-in hitting that figure received 7% off. Core loyalty has no
partner-attribute condition, so the gate has to live in code.

The override is deliberately narrow: it filters one named program and leaves
every other program's applicability untouched.
"""

import logging

from odoo import models

_logger = logging.getLogger(__name__)

VIP_PROGRAM_NAME = 'VIP Instant Discount'
ELIGIBLE_TIERS = ('vip', 'vvip')


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _get_applicable_programs(self):
        programs = super()._get_applicable_programs()

        gated = programs.filtered(lambda p: p.name == VIP_PROGRAM_NAME)
        if not gated:
            return programs

        # Odoo calls this per order, but nothing guarantees it. On a multi-record
        # set "the customer's tier" has no single answer, so withhold rather
        # than guess: a discount wrongly granted is harder to undo than one a
        # manager applies by hand.
        if len(self) != 1:
            return programs - gated

        tier = self.partner_id.x_vip_tier if self.partner_id else False
        if tier in ELIGIBLE_TIERS:
            return programs

        _logger.debug(
            "Samra CRM: withholding %s from %s (tier %s)",
            VIP_PROGRAM_NAME, self.partner_id.display_name, tier or 'regular')
        return programs - gated
