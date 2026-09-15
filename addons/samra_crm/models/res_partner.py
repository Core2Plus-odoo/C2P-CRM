# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # --- VIP / Clienteling ---
    x_vip_tier = fields.Selection(
        [('regular', 'Regular'), ('vip', 'VIP'), ('vvip', 'VVIP')],
        string='VIP Tier',
        tracking=True,
        help='Customer tier — set manually or promoted from Lifetime Value via a scheduled action.',
    )
    x_anniversary = fields.Date(string='Anniversary')

    # --- Jewellery Preferences ---
    x_gold_colour_pref = fields.Selection(
        [('yellow', 'Yellow Gold'), ('white', 'White Gold'), ('rose', 'Rose Gold')],
        string='Preferred Gold Colour',
    )
    x_jewellery_category_pref = fields.Char(string='Preferred Category')
    x_collection_pref = fields.Char(string='Preferred Collection')
    x_size_pref = fields.Char(string='Preferred Size')
    x_diamond_spec_pref = fields.Char(string='Diamond Specification Preference')
    x_budget_pref = fields.Float(string='Budget Preference (AED)')

    # --- Marketing Consent ---
    x_whatsapp_consent = fields.Boolean(string='WhatsApp Marketing Consent')
    x_sms_consent = fields.Boolean(string='SMS Marketing Consent')

    # --- Purchase Analytics ---
    # NOTE: populated by a scheduled action / cron in this version, not a live computed
    # field, to keep write performance predictable on large order histories. A future
    # iteration can convert these to `compute=` fields with `store=True` if real-time
    # accuracy becomes a requirement.
    x_lifetime_value = fields.Float(string='Lifetime Value (AED)')
    x_purchase_frequency = fields.Integer(string='Purchase Frequency')
    x_last_purchase_date = fields.Date(string='Last Purchase Date')
