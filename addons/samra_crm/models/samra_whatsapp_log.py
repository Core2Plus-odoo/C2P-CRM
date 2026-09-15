# -*- coding: utf-8 -*-
from odoo import fields, models


class SamraWhatsappLog(models.Model):
    _name = 'x_samra_whatsapp_log'
    _description = 'Samra WhatsApp Message Log'
    _order = 'x_message_date desc'

    x_name = fields.Char(string='Name')
    x_partner_id = fields.Many2one('res.partner', string='Customer')
    x_direction = fields.Selection(
        [('outbound', 'Outbound'), ('inbound', 'Inbound')],
        string='Direction',
    )
    x_message_type = fields.Selection(
        [
            ('chat', 'General Chat'),
            ('product_share', 'Product Share'),
            ('invoice_share', 'Invoice Share'),
            ('campaign', 'Campaign'),
        ],
        string='Message Type',
    )
    x_content = fields.Text(string='Message Content')
    x_product_id = fields.Many2one('product.product', string='Related Product')
    x_message_date = fields.Datetime(string='Message Date')

    # --- Integration hook -------------------------------------------------
    # This model currently only LOGS messages (mock/demo integration). To wire
    # in a real WhatsApp Business API (Meta Cloud API, Twilio, or 360dialog),
    # add a `send_whatsapp_message()` method here that calls the provider's
    # API, then have the UI buttons on res.partner / product / invoice call it
    # instead of (or in addition to) creating a log entry directly.
