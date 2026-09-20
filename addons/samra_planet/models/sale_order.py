# -*- coding: utf-8 -*-
"""Issue a tax-free tag when a tourist's sale is confirmed.

Unlike AML, a failure here never blocks the sale. A tourist not getting a
tag immediately is corrected by hand later; refusing a paid, confirmed sale
over Planet being unreachable would be the worse failure -- the same
reasoning samra_aml uses the other way round for a compliance block.
"""

from odoo import _, api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_planet_issuance_count = fields.Integer(compute='_compute_planet_issuance_count')

    @api.depends('name')
    def _compute_planet_issuance_count(self):
        # Keyed on the order reference, not a foreign key -- see
        # samra_planet_issuance.py for why the two are not linked directly.
        counts = dict(self.env['samra.planet.issuance']._read_group(
            [('order_ref', 'in', self.mapped('name'))],
            ['order_ref'], ['__count'],
        ))
        for order in self:
            order.x_planet_issuance_count = counts.get(order.name, 0)

    def action_open_planet_issuances(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Tax-Free Issuances"),
            'res_model': 'samra.planet.issuance',
            'view_mode': 'list,form',
            'domain': [('order_ref', '=', self.name)],
        }

    def action_confirm(self):
        result = super().action_confirm()
        for order in self:
            if order.partner_id.x_planet_is_tourist:
                order._samra_planet_issue()
        return result

    def _samra_planet_issue(self):
        self.ensure_one()
        provider = self.env['samra.planet.provider']._active_provider()
        if not provider:
            return False
        outcome = provider.issue(self)
        return self.env['samra.planet.issuance']._record(self, provider, outcome)
