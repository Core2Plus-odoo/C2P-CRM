# -*- coding: utf-8 -*-
"""Generate six months of representative Samra trading data.

Run explicitly from Samra CRM -> Generate Demo Data. It is a wizard rather
than a demo/ data file on purpose: Odoo only loads demo data when a database
is created with it, which this one was not, and a file that seeds hundreds of
orders is not something that should sit one upgrade away from a production
install.

Everything it writes is tagged, so a second run can clear the first rather
than doubling the history.
"""

import logging
import random
from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .samra_metrics import CONFIRMED_STATES

_logger = logging.getLogger(__name__)

# Marks generated orders so a re-run can find and remove them.
DEMO_REF_PREFIX = 'DEMO-'

# A fixed seed keeps runs reproducible: the same instance regenerates the same
# history, so a figure quoted in a meeting is still there the next morning.
SEED = 20260915

COLLECTIONS = ['Heritage', 'Bridal', 'Solitaire', 'Everyday', 'Celeste']
STYLES = ['Classic', 'Contemporary', 'Art Deco', 'Minimal']
GEMSTONES = ['Emerald', 'Ruby', 'Sapphire', 'Pearl', '']
CLARITY = ['VVS1 D', 'VVS2 E', 'VS1 F', 'VS2 G', 'SI1 H']
CUTS = ['round brilliant', 'oval', 'princess', 'emerald cut', 'pear']

WHATSAPP_OUT = [
    "Good morning — the piece you asked about has arrived in store.",
    "Sharing the new Heritage collection photographs with you.",
    "Your invoice is attached. Thank you for visiting us today.",
    "We are holding this under your name until the weekend.",
    "A private viewing is available Thursday evening if that suits.",
]
WHATSAPP_IN = [
    "Wonderful. Can you hold it until the weekend?",
    "Could you send the price for the matching earrings?",
    "Thank you — I will come by on Saturday.",
    "Is this available in yellow gold?",
]

WISHLIST_NOTES = [
    'Mentioned for Eid', 'Anniversary', 'Matches a previous purchase',
    'Considering for daughter', 'Wants to see in person', '',
]


class SamraDemoData(models.TransientModel):
    _name = 'samra.demo.data'
    _description = 'Generate Samra Demo Data'

    months = fields.Integer(string='Months of History', default=6, required=True)
    order_count = fields.Integer(string='Orders to Create', default=120, required=True)
    enrich_products = fields.Boolean(
        string='Fill in Jewellery Specifications', default=True,
        help='Sets collection, style, gemstone, gold weight and stone details on '
             'products that have none. Without these the profile\'s collection '
             'breakdown and gold figures stay empty.',
    )
    with_engagement = fields.Boolean(
        string='Wishlist, Viewings and Messages', default=True)
    with_occasions = fields.Boolean(
        string='Birthdays and Anniversaries', default=True,
        help='Fills in dates of birth and wedding anniversaries on customers '
             'that have none, weighted so that a workable number of them fall '
             'in the coming weeks. Without these the Upcoming Occasions list '
             'is empty however many orders exist.',
    )
    clear_previous = fields.Boolean(
        string='Remove Previously Generated Orders', default=True,
        help='Deletes orders from an earlier run so history does not double up. '
             'Only touches orders this wizard created.',
    )

    # ------------------------------------------------------------------

    def _rng(self):
        return random.Random(SEED)

    def _demo_order_domain(self):
        return [('client_order_ref', '=like', f'{DEMO_REF_PREFIX}%')]

    # ------------------------------------------------------------------

    def _enrich_products(self, rng):
        """Give products the specifications the profile reports on.

        Only fills blanks -- anything already set by hand is left alone, so a
        real catalogue is never overwritten by demo values.
        """
        templates = self.env['product.template'].search([('sale_ok', '=', True)])
        touched = 0
        for index, template in enumerate(templates):
            values = {}
            if not template.x_collection:
                values['x_collection'] = COLLECTIONS[index % len(COLLECTIONS)]
            if not template.x_style:
                values['x_style'] = STYLES[index % len(STYLES)]
            if not template.x_gemstone:
                stone = GEMSTONES[index % len(GEMSTONES)]
                if stone:
                    values['x_gemstone'] = stone
            if not template.x_gold_weight:
                values['x_gold_weight'] = round(rng.uniform(3.5, 62.0), 2)
            if not template.x_stone_details:
                carat = round(rng.uniform(0.25, 2.4), 2)
                values['x_stone_details'] = (
                    f"{carat}ct {rng.choice(CLARITY)}, {rng.choice(CUTS)}")
            if values:
                template.write(values)
                touched += 1
        return touched

    def _pick_customers(self, rng):
        """Weight a few customers heavily, as real clienteling data is.

        A flat distribution would make every customer look identical and the
        VIP breakdowns meaningless.
        """
        customers = self.env['res.partner'].search(
            self.env['res.partner']._samra_customer_domain(), order='id')
        if not customers:
            raise UserError(_("No customers found. Create some contacts first."))

        weighted = []
        for index, partner in enumerate(customers):
            weight = 6 if index < 3 else (3 if index < 12 else 1)
            weighted.extend([partner.id] * weight)
        return customers, weighted

    def _generate_orders(self, rng, products, warehouses, salespeople, weighted):
        Order = self.env['sale.order']
        start = fields.Datetime.now() - timedelta(days=self.months * 30)
        span = self.months * 30
        created = Order.browse()

        for sequence in range(self.order_count):
            partner = self.env['res.partner'].browse(rng.choice(weighted))
            when = start + timedelta(
                days=rng.randint(0, span), hours=rng.randint(10, 21))

            lines = []
            per_order = min(rng.randint(1, 3), len(products))
            for product in rng.sample(list(products), per_order):
                lines.append((0, 0, {
                    'product_id': product.id,
                    'product_uom_qty': 1,
                }))

            order = Order.create({
                'partner_id': partner.id,
                'client_order_ref': f'{DEMO_REF_PREFIX}{sequence + 1:04d}',
                'warehouse_id': rng.choice(warehouses).id,
                'user_id': rng.choice(salespeople).id,
            })
            order.write({'order_line': lines})

            # Written rather than confirmed through the workflow: confirming
            # 120 orders would generate 120 deliveries on a demo database and
            # take minutes. The state is what every report reads.
            order.write({'state': 'sale'})
            # Dated separately, after the state has settled. The field is plain
            # and writable, but the spread of these dates is the entire point
            # of the exercise -- a combined write leaves the ordering to the
            # ORM, and every order landing on today collapses the trend chart
            # into a single column.
            order.write({'date_order': when})
            created |= order

        return created

    def _generate_engagement(self, rng, customers, products, warehouses):
        Wishlist = self.env['x_samra_wishlist']
        Viewed = self.env['x_samra_viewed_product']
        Messages = self.env['x_samra_whatsapp_log']
        now = fields.Datetime.now()
        counts = {'wishlist': 0, 'viewed': 0, 'messages': 0}

        for index, partner in enumerate(customers):
            # Not everyone is engaged; a database where every customer has a
            # wishlist tells you nothing about who to call.
            if index >= 3 and rng.random() > 0.55:
                continue

            wanted = min(rng.randint(1, 4), len(products))
            for product in rng.sample(list(products), wanted):
                Wishlist.create({
                    'x_name': product.display_name,
                    'x_partner_id': partner.id,
                    'x_product_id': product.id,
                    'x_price': product.list_price,
                    'x_date_added': fields.Date.to_string(
                        (now - timedelta(days=rng.randint(1, 160))).date()),
                    'x_note': rng.choice(WISHLIST_NOTES),
                })
                counts['wishlist'] += 1

            wanted = min(rng.randint(2, 8), len(products))
            for product in rng.sample(list(products), wanted):
                Viewed.create({
                    'x_name': product.display_name,
                    'x_partner_id': partner.id,
                    'x_product_id': product.id,
                    'x_view_date': now - timedelta(days=rng.randint(1, 170)),
                    'x_branch_id': rng.choice(warehouses).id,
                })
                counts['viewed'] += 1

            outbound = True
            stamp = now - timedelta(days=rng.randint(2, 120))
            for _index in range(rng.randint(2, 8)):
                Messages.create({
                    'x_name': partner.display_name,
                    'x_partner_id': partner.id,
                    'x_direction': 'outbound' if outbound else 'inbound',
                    'x_message_type': rng.choice(
                        ['chat', 'product_share', 'invoice_share', 'campaign']),
                    'x_content': rng.choice(WHATSAPP_OUT if outbound else WHATSAPP_IN),
                    'x_message_date': stamp,
                })
                counts['messages'] += 1
                outbound = not outbound
                stamp += timedelta(hours=rng.randint(1, 30))

        return counts

    @staticmethod
    def _shift_years(when, years):
        """Move a date back N years, surviving 29 February."""
        try:
            return when.replace(year=when.year - years)
        except ValueError:
            return when.replace(year=when.year - years, day=28)

    def _generate_occasions(self, rng, customers):
        """Give customers birthdays and anniversaries worth acting on.

        Dates scattered uniformly across the year would leave roughly one
        customer in twelve with an occasion this month, which is honest but
        useless for looking at the feature. So a deliberate share of them are
        placed in the next six weeks: enough to fill the worklist without
        making every customer an occasion, which would be its own kind of lie.

        Only writes where the field is empty. A date somebody entered by hand
        is real data and the demo generator has no business overwriting it.
        """
        today = fields.Date.context_today(self)
        filled = {'birthday': 0, 'anniversary': 0}

        for partner in customers:
            if not partner.x_birthday:
                if rng.random() < 0.35:
                    # Soon: inside the window the list is organised around.
                    when = today + timedelta(days=rng.randint(0, 45))
                else:
                    when = today + timedelta(days=rng.randint(46, 364))
                # Push it back a plausible lifetime so the stored value reads
                # as a date of birth rather than a date in the future.
                born = self._shift_years(when, rng.randint(24, 62))
                partner.x_birthday = born
                filled['birthday'] += 1

            # Not everyone is married, and a database where they all are makes
            # the anniversary column meaningless.
            if not partner.x_anniversary and rng.random() < 0.6:
                if rng.random() < 0.3:
                    when = today + timedelta(days=rng.randint(0, 45))
                else:
                    when = today + timedelta(days=rng.randint(46, 364))
                married = self._shift_years(when, rng.randint(1, 30))
                partner.x_anniversary = married
                filled['anniversary'] += 1

        return filled

    # ------------------------------------------------------------------

    def action_generate(self):
        self.ensure_one()

        if not self.env.user.has_group('sales_team.group_sale_manager'):
            raise UserError(_("Only Sales managers can generate demo data."))
        if self.months < 1 or self.order_count < 1:
            raise UserError(_("Months and order count must both be at least 1."))

        rng = self._rng()

        products = self.env['product.product'].search([('sale_ok', '=', True)])
        if not products:
            raise UserError(_("No saleable products found. Create products first."))

        warehouses = self.env['stock.warehouse'].search([])
        if not warehouses:
            raise UserError(_("No warehouses configured."))

        salespeople = self.env['res.users'].search([('share', '=', False)], limit=10)
        if not salespeople:
            raise UserError(_("No internal users found to assign orders to."))

        # Orders this wizard did not create are counted by every dashboard
        # figure but are invisible to the cleanup below, which is scoped to the
        # DEMO- prefix. Reporting the number is the difference between a total
        # that reconciles and one that quietly includes somebody's test run.
        foreign = self.env['sale.order'].search_count([
            ('state', 'in', list(CONFIRMED_STATES)),
            '|',
            ('client_order_ref', '=', False),
            ('client_order_ref', 'not like', f'{DEMO_REF_PREFIX}%'),
        ])

        removed = 0
        if self.clear_previous:
            previous = self.env['sale.order'].search(self._demo_order_domain())
            removed = len(previous)
            if previous:
                # Back to draft first: Odoo refuses to unlink a confirmed order.
                previous.write({'state': 'draft'})
                previous.unlink()

        enriched = self._enrich_products(rng) if self.enrich_products else 0

        customers, weighted = self._pick_customers(rng)
        orders = self._generate_orders(rng, products, warehouses, salespeople, weighted)

        engagement = {'wishlist': 0, 'viewed': 0, 'messages': 0}
        if self.with_engagement:
            engagement = self._generate_engagement(rng, customers, products, warehouses)

        occasions = {'birthday': 0, 'anniversary': 0}
        if self.with_occasions:
            occasions = self._generate_occasions(rng, customers)

        # The profile reads live, but list views, search and the dashboard read
        # the stored fields -- so refresh them rather than leaving the two
        # disagreeing until the nightly run.
        #
        # The on-demand method, not the cron one: the cron commits per batch,
        # which is right for a scheduled job and wrong inside a request, where
        # it would give up the rollback protecting everything above it.
        customers.action_samra_recompute_metrics()

        _logger.info(
            "Samra demo data: %s orders, %s products enriched, %s removed",
            len(orders), enriched, removed)

        message = _(
            "%(orders)s orders created across %(months)s months.\n"
            "%(enriched)s products given specifications.\n"
            "%(wishlist)s wishlist items, %(viewed)s viewings, %(messages)s messages.\n"
            "%(birthdays)s birthdays and %(anniversaries)s anniversaries filled in.\n"
            "%(removed)s previously generated orders removed.\n"
            "%(foreign)s confirmed orders were not created here and were left "
            "alone -- dashboard totals include them.\n"
            "Customer metrics recomputed.",
            orders=len(orders), months=self.months, enriched=enriched,
            wishlist=engagement['wishlist'], viewed=engagement['viewed'],
            messages=engagement['messages'], removed=removed, foreign=foreign,
            birthdays=occasions['birthday'], anniversaries=occasions['anniversary'],
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Demo data generated"),
                'message': message,
                'type': 'success',
                'sticky': True,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
