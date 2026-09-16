# -*- coding: utf-8 -*-
"""Occasions, the customer domain, and recommendations.

The customer domain gets a test because its predecessor matched nothing on the
live database and did so silently: no lifetime value was ever written, so
nobody was ever tiered, and every figure downstream read as a legitimate zero.
A domain that can be wrong without anything breaking is a domain that needs an
assertion.
"""

from datetime import date, timedelta

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCustomerDomain(TransactionCase):

    def test_a_contact_with_no_orders_still_counts(self):
        """customer_rank only moves through Odoo's own sale flow.

        Samra's address book was built by import and at the till, so a domain
        keyed on rank matched nobody at all.
        """
        walk_in = self.env['res.partner'].create({'name': 'Walk-in Customer'})
        found = self.env['res.partner'].search(
            self.env['res.partner']._samra_customer_domain())
        self.assertIn(walk_in, found)
        self.assertEqual(walk_in.customer_rank, 0,
                         "precondition: this contact never bought anything")

    def test_an_internal_user_is_not_a_customer(self):
        staff = self.env['res.users'].search([('share', '=', False)], limit=1)
        found = self.env['res.partner'].search(
            self.env['res.partner']._samra_customer_domain())
        self.assertNotIn(staff.partner_id, found)

    def test_an_invoice_address_is_not_a_customer(self):
        parent = self.env['res.partner'].create({'name': 'Parent Co'})
        address = self.env['res.partner'].create({
            'name': 'Billing', 'type': 'invoice', 'parent_id': parent.id})
        found = self.env['res.partner'].search(
            self.env['res.partner']._samra_customer_domain())
        self.assertNotIn(address, found)


@tagged('post_install', '-at_install')
class TestOccasions(TransactionCase):

    def setUp(self):
        super().setUp()
        self.today = date.today()
        self.partner = self.env['res.partner'].create({'name': 'Occasion Test'})

    def _birthday_in(self, days, years_ago=35):
        when = self.today + timedelta(days=days)
        return when.replace(year=when.year - years_ago)

    def test_a_birthday_projects_to_its_next_occurrence(self):
        self.partner.x_birthday = self._birthday_in(9)
        self.assertEqual(self.partner.x_days_to_occasion, 9)
        self.assertEqual(self.partner.x_next_occasion_type, 'birthday')

    def test_a_leap_day_stays_in_february(self):
        """1 March would move the occasion into the wrong month, and the
        whole feature is organised around month boundaries."""
        self.partner.x_anniversary = date(2016, 2, 29)
        self.assertEqual(self.partner.x_anniversary_next.month, 2)
        self.assertIn(self.partner.x_anniversary_next.day, (28, 29))

    def test_no_dates_means_no_occasion(self):
        self.assertFalse(self.partner.x_next_occasion_date)
        self.assertEqual(self.partner.x_days_to_occasion, 0)

    def test_the_soonest_occasion_wins(self):
        self.partner.write({
            'x_birthday': self._birthday_in(40),
            'x_anniversary': self._birthday_in(5, years_ago=10),
        })
        self.assertEqual(self.partner.x_next_occasion_type, 'anniversary')
        self.assertEqual(self.partner.x_days_to_occasion, 5)

    def test_upcoming_list_is_soonest_first(self):
        far = self.env['res.partner'].create(
            {'name': 'Far', 'x_birthday': self._birthday_in(25)})
        near = self.env['res.partner'].create(
            {'name': 'Near', 'x_birthday': self._birthday_in(2)})
        rows = self.env['res.partner'].samra_upcoming_occasions(days=30)
        ids = [row['id'] for row in rows['occasions']]
        self.assertLess(ids.index(near.id), ids.index(far.id))

    def test_the_occasion_views_are_not_the_default_partner_views(self):
        """ir.ui.view._order is priority,name,id -- at equal priority the name
        decides, and res.partner.samra.occasions.* sorts ahead of
        res.partner.tree and res.partner.select. Left at 16 these became the
        default list and search for every partner screen in the database."""
        View = self.env['ir.ui.view']
        for view_type in ('list', 'search'):
            chosen = View.browse(View.default_view('res.partner', view_type))
            self.assertNotIn('samra', chosen.name or '')


@tagged('post_install', '-at_install')
class TestRecommendations(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        category = cls.env['product.category'].create({'name': 'Test Rings'})

        def product(name, price):
            return cls.env['product.product'].create({
                'name': name, 'list_price': price, 'sale_ok': True,
                'categ_id': category.id})

        cls.owned = product('Owned Solitaire', 30000)
        cls.wished = product('Wished Pendant', 28000)
        cls.grail = product('Imperial Necklace', 900000)

        cls.customer = cls.env['res.partner'].create({'name': 'Rec Test'})
        order = cls.env['sale.order'].create({
            'partner_id': cls.customer.id,
            'order_line': [(0, 0, {'product_id': cls.owned.id,
                                   'product_uom_qty': 1})]})
        order.action_confirm()

        cls.env['x_samra_wishlist'].create({
            'x_name': cls.wished.display_name,
            'x_partner_id': cls.customer.id,
            'x_product_id': cls.wished.id,
            'x_price': cls.wished.list_price})

    def test_a_wishlisted_piece_leads(self):
        rows = self.customer._samra_recommendations()['products']
        self.assertTrue(rows)
        self.assertEqual(rows[0]['id'], self.wished.id)
        self.assertTrue(rows[0]['reasons'], "a recommendation with no reason")

    def test_what_she_already_owns_is_never_suggested(self):
        """A second identical ring is an embarrassing suggestion, not a sale."""
        ids = [row['id']
               for row in self.customer._samra_recommendations()['products']]
        self.assertNotIn(self.owned.id, ids)

    def test_far_out_of_budget_is_dropped(self):
        ids = [row['id']
               for row in self.customer._samra_recommendations()['products']]
        self.assertNotIn(self.grail.id, ids)

    def test_a_customer_with_no_history_is_safe(self):
        stranger = self.env['res.partner'].create({'name': 'Brand New'})
        result = stranger._samra_recommendations()
        self.assertEqual(result['products'], [])
