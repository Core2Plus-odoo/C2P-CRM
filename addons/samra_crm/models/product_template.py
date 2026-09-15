# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    """Jewellery specifications.

    Gold Colour, Karat and Stone are already modelled as product attributes
    (they drive variant generation). These are per-item specifications that do
    not vary the SKU but must appear on a purchase-history line: requirement 2
    asks for gold weight and diamond/stone details against every purchase.
    """
    _inherit = 'product.template'

    x_gold_weight = fields.Float(
        string='Gold Weight (g)',
        digits=(16, 3),
        help='Net gold weight in grams, as printed on the certificate.',
    )
    x_stone_details = fields.Char(
        string='Diamond / Stone Details',
        help='Free-text certificate summary, e.g. "0.75ct VS1 F, round brilliant".',
    )
    x_gemstone = fields.Char(string='Gemstone')
    x_style = fields.Char(string='Style')
    x_collection = fields.Char(string='Collection')
