# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo import _, fields, models

# A customer who has not bought in this many days is surfaced as "at risk" on
# the profile and feeds the dashboard's reactivation list.
AT_RISK_DAYS = 90

# How much history the profile shows before the user drills through.
PROFILE_ORDER_LIMIT = 10
PROFILE_LIST_LIMIT = 8


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
    x_birthday = fields.Date(string='Birthday')
    x_nationality_id = fields.Many2one('res.country', string='Nationality')
    # Notes reuse res.partner.comment rather than adding a parallel field.

    # --- Jewellery Preferences ---
    x_gold_colour_pref = fields.Selection(
        [('yellow', 'Yellow Gold'), ('white', 'White Gold'), ('rose', 'Rose Gold')],
        string='Preferred Gold Colour',
    )
    x_jewellery_category_pref = fields.Char(string='Preferred Category')
    x_collection_pref = fields.Char(string='Preferred Collection')
    x_size_pref = fields.Char(string='Preferred Size')
    x_diamond_spec_pref = fields.Char(string='Diamond Specification Preference')
    x_gemstone_pref = fields.Char(string='Preferred Gemstone')
    x_style_pref = fields.Char(string='Preferred Style')
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

    # ------------------------------------------------------------------
    # Customer 360 profile
    # ------------------------------------------------------------------

    def action_open_samra_profile(self):
        """Open the bespoke clienteling profile for this customer."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'samra_customer_360',
            'name': _('Customer 360'),
            'params': {'partner_id': self.id},
        }

    def _samra_days_since_purchase(self):
        self.ensure_one()
        if not self.x_last_purchase_date:
            return None
        return (date.today() - self.x_last_purchase_date).days

    def _samra_loyalty(self):
        """Points balance and the rewards this balance can actually buy."""
        self.ensure_one()
        if 'loyalty.card' not in self.env:
            return {'points': 0.0, 'rewards': []}

        cards = self.env['loyalty.card'].search([('partner_id', '=', self.id)])
        points = sum(cards.mapped('points'))

        rewards = []
        for reward in cards.mapped('program_id.reward_ids'):
            rewards.append({
                'id': reward.id,
                'description': reward.display_name,
                'required_points': reward.required_points,
                'affordable': points >= reward.required_points,
            })
        rewards.sort(key=lambda r: r['required_points'])
        return {'points': points, 'rewards': rewards}

    def _samra_orders(self, limit=PROFILE_ORDER_LIMIT):
        """Purchase history, detailed to the level a jeweller actually needs.

        Requirement 2 asks for invoice number, branch, salesperson, SKU,
        description, quantity, price, gold weight, stone details and total --
        so lines carry the certificate specifications, not just a product name.
        """
        self.ensure_one()
        orders = self.env['sale.order'].search(
            [('partner_id', '=', self.id), ('state', 'not in', ('draft', 'cancel'))],
            order='date_order desc', limit=limit,
        )
        return [{
            'id': order.id,
            'name': order.name,
            'invoices': order.invoice_ids.mapped('name'),
            'date': fields.Date.to_string(order.date_order) if order.date_order else None,
            'amount_total': order.amount_total,
            'state': order.state,
            'branch': order.warehouse_id.display_name or '',
            'salesperson': order.user_id.display_name or '',
            'lines': [{
                'product_id': line.product_id.id,
                'sku': line.product_id.default_code or '',
                'description': line.product_id.display_name or line.name or '',
                'qty': line.product_uom_qty,
                'price': line.price_unit,
                'subtotal': line.price_subtotal,
                'gold_weight': line.product_id.x_gold_weight,
                'stone_details': line.product_id.x_stone_details or '',
            } for line in order.order_line if line.product_id and not line.display_type],
        } for order in orders]

    def _samra_wishlist(self, limit=PROFILE_LIST_LIMIT):
        self.ensure_one()
        records = self.env['x_samra_wishlist'].search(
            [('x_partner_id', '=', self.id)], limit=limit)
        return [{
            'id': rec.id,
            'product_id': rec.x_product_id.id,
            'product': rec.x_product_id.display_name or rec.x_name or '',
            'price': rec.x_price,
            'date_added': fields.Date.to_string(rec.x_date_added) if rec.x_date_added else None,
            'note': rec.x_note or '',
        } for rec in records]

    def _samra_viewed(self, limit=PROFILE_LIST_LIMIT):
        self.ensure_one()
        records = self.env['x_samra_viewed_product'].search(
            [('x_partner_id', '=', self.id)], limit=limit)
        return [{
            'id': rec.id,
            'product_id': rec.x_product_id.id,
            'product': rec.x_product_id.display_name or rec.x_name or '',
            'branch': rec.x_branch_id.display_name or '',
            'viewed_on': fields.Datetime.to_string(rec.x_view_date) if rec.x_view_date else None,
        } for rec in records]

    def _samra_whatsapp(self, limit=PROFILE_LIST_LIMIT):
        self.ensure_one()
        records = self.env['x_samra_whatsapp_log'].search(
            [('x_partner_id', '=', self.id)], limit=limit)
        return [{
            'id': rec.id,
            'direction': rec.x_direction or 'outbound',
            'message_type': rec.x_message_type or '',
            'content': rec.x_content or '',
            'product': rec.x_product_id.display_name or '',
            'date': fields.Datetime.to_string(rec.x_message_date) if rec.x_message_date else None,
        } for rec in records]

    def _samra_appointments(self, limit=5):
        """Upcoming meetings, so the associate sees them without leaving the profile."""
        self.ensure_one()
        if 'calendar.event' not in self.env:
            return []
        events = self.env['calendar.event'].search(
            [('partner_ids', 'in', self.id), ('start', '>=', fields.Datetime.now())],
            order='start asc', limit=limit,
        )
        return [{
            'id': event.id,
            'name': event.name,
            'start': fields.Datetime.to_string(event.start) if event.start else None,
            'location': event.location or '',
        } for event in events]

    def _samra_tickets(self, limit=5):
        """Open helpdesk tickets. Helpdesk is Enterprise-only, so degrade quietly."""
        self.ensure_one()
        if 'helpdesk.ticket' not in self.env:
            return []
        tickets = self.env['helpdesk.ticket'].search(
            [('partner_id', '=', self.id), ('stage_id.fold', '=', False)],
            order='create_date desc', limit=limit,
        )
        return [{
            'id': ticket.id,
            'name': ticket.name,
            'stage': ticket.stage_id.display_name or '',
            'created': fields.Date.to_string(ticket.create_date) if ticket.create_date else None,
        } for ticket in tickets]

    # ------------------------------------------------------------------
    # Showing-room capture
    # ------------------------------------------------------------------

    def _samra_default_branch(self):
        """The branch the logged-in associate is standing in.

        Taken from their default warehouse, falling back to the company's
        first. An associate should never have to tell the system where they
        are -- they are holding a tray.
        """
        user = self.env.user
        warehouse = self.env['stock.warehouse']
        if 'property_warehouse_id' in user._fields:
            warehouse = user.property_warehouse_id
        if not warehouse:
            warehouse = warehouse.search(
                [('company_id', '=', self.env.company.id)], limit=1)
        return warehouse

    def samra_search_products(self, query, limit=24):
        """Product lookup for the capture panel.

        Matches on name, internal reference and barcode in one pass, so a
        scanner gun and a typed fragment go down the same path -- the scanner
        just types faster.
        """
        self.ensure_one()
        query = (query or '').strip()
        domain = [('sale_ok', '=', True)]
        if query:
            domain += ['|', '|',
                       ('name', 'ilike', query),
                       ('default_code', 'ilike', query),
                       ('barcode', '=', query)]

        products = self.env['product.product'].search(domain, limit=limit)
        return [{
            'id': product.id,
            'name': product.display_name,
            'sku': product.default_code or '',
            'price': product.list_price,
        } for product in products]

    def samra_log_viewed(self, product_ids, to_wishlist=False):
        """Record a tray of products in one write.

        Called once when the associate finishes showing, not once per item:
        `x_view_date` and `x_branch_id` are filled in from the clock and the
        user's branch rather than asked for. `to_wishlist` handles the natural
        escalation -- the customer liked one -- without a second screen.
        """
        self.ensure_one()
        product_ids = [int(pid) for pid in (product_ids or [])]
        if not product_ids:
            return {'viewed': 0, 'wishlisted': 0}

        products = self.env['product.product'].browse(product_ids).exists()
        branch = self._samra_default_branch()
        now = fields.Datetime.now()

        self.env['x_samra_viewed_product'].create([{
            'x_name': product.display_name,
            'x_partner_id': self.id,
            'x_product_id': product.id,
            'x_view_date': now,
            'x_branch_id': branch.id or False,
        } for product in products])

        wishlisted = 0
        if to_wishlist:
            # Don't duplicate something already on the wishlist -- an associate
            # showing a piece twice shouldn't create two entries.
            existing = self.env['x_samra_wishlist'].search([
                ('x_partner_id', '=', self.id),
                ('x_product_id', 'in', products.ids),
            ]).mapped('x_product_id').ids
            fresh = products.filtered(lambda p: p.id not in existing)
            if fresh:
                self.env['x_samra_wishlist'].create([{
                    'x_name': product.display_name,
                    'x_partner_id': self.id,
                    'x_product_id': product.id,
                    'x_price': product.list_price,
                    'x_date_added': fields.Date.context_today(self),
                } for product in fresh])
            wishlisted = len(fresh)

        return {
            'viewed': len(products),
            'wishlisted': wishlisted,
            'branch': branch.display_name or '',
        }

    def get_samra_profile(self):
        """Everything the 360 profile renders, in a single round trip.

        The profile shows a dozen related record sets. Fetching them one
        read_group at a time from the browser would mean a dozen sequential
        RPCs before anything paints.
        """
        self.ensure_one()
        days_since = self._samra_days_since_purchase()

        return {
            'id': self.id,
            'name': self.display_name,
            'avatar': f'/web/image/res.partner/{self.id}/avatar_128',
            'vip_tier': self.x_vip_tier or 'regular',
            'vip_tier_label': dict(self._fields['x_vip_tier'].selection).get(
                self.x_vip_tier, _('Regular')),
            'salesperson': self.user_id.display_name or '',
            'salesperson_id': self.user_id.id,
            'email': self.email or '',
            'phone': self.phone or '',
            'mobile': self.mobile or self.phone or '',
            'city': self.city or '',
            'tags': [{'id': tag.id, 'name': tag.name, 'color': tag.color} for tag in self.category_id],
            'anniversary': fields.Date.to_string(self.x_anniversary) if self.x_anniversary else None,
            'birthday': fields.Date.to_string(self.x_birthday) if self.x_birthday else None,
            'nationality': self.x_nationality_id.name or '',
            'notes': self.comment or '',
            'consent': {
                'whatsapp': self.x_whatsapp_consent,
                'sms': self.x_sms_consent,
            },
            'stats': {
                'lifetime_value': self.x_lifetime_value,
                'purchase_frequency': self.x_purchase_frequency,
                'last_purchase_date': fields.Date.to_string(self.x_last_purchase_date)
                                      if self.x_last_purchase_date else None,
                'days_since_purchase': days_since,
                'at_risk': days_since is not None and days_since >= AT_RISK_DAYS,
                'never_purchased': self.x_last_purchase_date is False or not self.x_last_purchase_date,
            },
            'preferences': {
                'gold_colour': dict(self._fields['x_gold_colour_pref'].selection).get(
                    self.x_gold_colour_pref, ''),
                'category': self.x_jewellery_category_pref or '',
                'collection': self.x_collection_pref or '',
                'size': self.x_size_pref or '',
                'diamond_spec': self.x_diamond_spec_pref or '',
                'gemstone': self.x_gemstone_pref or '',
                'style': self.x_style_pref or '',
                'budget': self.x_budget_pref,
            },
            'loyalty': self._samra_loyalty(),
            'orders': self._samra_orders(),
            'wishlist': self._samra_wishlist(),
            'viewed': self._samra_viewed(),
            'whatsapp': self._samra_whatsapp(),
            'appointments': self._samra_appointments(),
            'tickets': self._samra_tickets(),
            'currency': self.env.company.currency_id.name or 'AED',
            'at_risk_days': AT_RISK_DAYS,
            'capture_branch': self._samra_default_branch().display_name or '',
        }
