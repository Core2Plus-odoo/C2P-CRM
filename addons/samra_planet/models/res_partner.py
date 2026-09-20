# -*- coding: utf-8 -*-
"""Whether this customer is a tourist, and the passport a refund files against.

Kept local to this module rather than shared with samra_aml's identity data
-- the two compliance workstreams have no reason to depend on each other, and
each stays installable without the other.
"""

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_planet_is_tourist = fields.Boolean(
        string='Tourist (Tax-Free Eligible)',
        help="A sale confirmed for this customer automatically requests a "
             "tax-free tag from the active Planet provider.")
    x_planet_passport_number = fields.Char(string='Passport Number')
    x_planet_issuance_ids = fields.One2many(
        'samra.planet.issuance', 'partner_id', string='Tax-Free Tags')
