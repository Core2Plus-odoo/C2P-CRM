# -*- coding: utf-8 -*-
from odoo import fields, models


class SamraViewedProduct(models.Model):
    _name = 'x_samra_viewed_product'
    _description = 'Samra Viewed Product Log'
    _order = 'x_view_date desc'

    x_name = fields.Char(string='Name')
    x_partner_id = fields.Many2one('res.partner', string='Customer')
    x_product_id = fields.Many2one('product.product', string='Product')
    x_view_date = fields.Datetime(string='Viewed On')
    x_branch_id = fields.Many2one('stock.warehouse', string='Branch')
