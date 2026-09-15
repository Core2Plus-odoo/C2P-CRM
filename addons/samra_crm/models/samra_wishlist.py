# -*- coding: utf-8 -*-
from odoo import fields, models


class SamraWishlist(models.Model):
    _name = 'x_samra_wishlist'
    _description = 'Samra Wishlist Item'
    _order = 'x_date_added desc'

    x_name = fields.Char(string='Name')
    x_partner_id = fields.Many2one('res.partner', string='Customer')
    x_product_id = fields.Many2one('product.product', string='Product')
    x_price = fields.Float(string='Price (AED)')
    x_date_added = fields.Date(string='Date Added')
    x_note = fields.Char(string='Note')
