# -*- coding: utf-8 -*-
"""The arithmetic a jeweller does on a calculator, asserted.

Every number here is one somebody could check by hand, and the comments give
the working, because a pricing test that only compares to a magic constant
tells the next reader nothing about whether the constant was ever right.
"""

from datetime import date, timedelta

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestGoldRate(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Rate = cls.env['samra.gold.rate']
        cls.today = date.today()
        cls.rate22 = cls.Rate.create({
            'rate_date': cls.today, 'karat': '22', 'rate_per_gram': 250.0,
            'source': 'Dubai Gold & Jewellery Group',
        })
        # 12g gross less 2g of stones is 10g of metal at 22K.
        cls.bangle = cls.env['product.template'].create({
            'name': 'Test Heritage Bangle 22K',
            'x_is_gold': True, 'x_karat': '22',
            'x_gross_weight': 12.0, 'x_stone_weight': 2.0,
            'x_wastage_pct': 8.0,
            'x_making_charge_type': 'per_gram', 'x_making_charge': 25.0,
            'x_stone_value': 1500.0, 'list_price': 1.0,
        })

    # -- reading the rate ---------------------------------------------

    def test_rate_read_back(self):
        self.assertAlmostEqual(self.Rate._rate_for('22'), 250.0, places=2)

    def test_rate_derived_from_another_karat(self):
        """18K is not quoted, so it scales off 22K by fineness."""
        self.assertAlmostEqual(
            self.Rate._rate_for('18'), 250.0 / 0.916 * 0.750, places=2)

    def test_rate_falls_back_to_an_earlier_day(self):
        """A public holiday must not leave the tills unable to price."""
        self.assertAlmostEqual(
            self.Rate._rate_for('22', on_date=self.today + timedelta(days=5)),
            250.0, places=2)

    def test_rate_is_zero_when_nothing_quoted(self):
        """Callers read 0 as 'no metal component', not as an error."""
        self.Rate.search([]).unlink()
        self.assertEqual(self.Rate._rate_for('22'), 0.0)

    # -- guards --------------------------------------------------------

    def test_one_rate_per_karat_per_day(self):
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.Rate.create({'rate_date': self.today, 'karat': '22',
                                  'rate_per_gram': 999.0})

    def test_rate_must_be_positive(self):
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                self.Rate.create({'rate_date': self.today - timedelta(days=1),
                                  'karat': '24', 'rate_per_gram': -5.0})

    def test_stones_cannot_outweigh_the_piece(self):
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                self.env['product.template'].create({
                    'name': 'Impossible', 'x_is_gold': True, 'x_karat': '22',
                    'x_gross_weight': 3.0, 'x_stone_weight': 5.0})

    # -- weights -------------------------------------------------------

    def test_net_and_fine_weight(self):
        self.assertAlmostEqual(self.bangle.x_net_weight, 10.0, places=3)
        # 10g of 22K is 9.16g of pure gold -- the figure that adds up across
        # karats, which net weight does not.
        self.assertAlmostEqual(self.bangle.x_fine_weight, 9.16, places=3)

    # -- the price -----------------------------------------------------

    def test_price_per_gram_making(self):
        # metal  10 x 250 x 1.08 = 2700
        # making 10 x 25         =  250
        # stones                 = 1500
        parts = self.bangle._samra_gold_parts()
        self.assertAlmostEqual(parts['metal'], 2700.0, places=2)
        self.assertAlmostEqual(parts['making'], 250.0, places=2)
        self.assertAlmostEqual(parts['total'], 4450.0, places=2)

    def test_price_flat_making(self):
        self.bangle.write({'x_making_charge_type': 'flat',
                           'x_making_charge': 800.0})
        self.assertAlmostEqual(
            self.bangle._samra_gold_parts()['making'], 800.0, places=2)

    def test_price_percent_making(self):
        self.bangle.write({'x_making_charge_type': 'percent',
                           'x_making_charge': 12.0})
        # 12% of 2700
        self.assertAlmostEqual(
            self.bangle._samra_gold_parts()['making'], 324.0, places=2)

    # -- applying ------------------------------------------------------

    def test_apply_writes_list_price_and_is_idempotent(self):
        self.assertTrue(self.bangle.x_price_is_stale)
        self.rate22.action_apply_to_products()
        self.bangle.invalidate_recordset()
        self.assertAlmostEqual(self.bangle.list_price, 4450.0, places=2)
        self.assertFalse(self.bangle.x_price_is_stale)

        # Applying again must write nothing: a rate run happens every morning
        # and should not put a tracking entry on every product every day.
        self.rate22.action_apply_to_products()
        self.assertEqual(self.rate22.applied_count, 0)

    def test_non_gold_products_are_untouched(self):
        plain = self.env['product.template'].create(
            {'name': 'Gift Box', 'list_price': 35.0})
        self.rate22.action_apply_to_products()
        plain.invalidate_recordset()
        self.assertAlmostEqual(plain.list_price, 35.0, places=2)
        self.assertEqual(plain.x_computed_price, 0.0)

    def test_apply_latest_skips_karats_with_no_products(self):
        """The cron path returns a value; it does not raise to find this out."""
        self.assertEqual(self.Rate.action_apply_latest(), ['22'])

    # -- multi-company --------------------------------------------------

    def test_rates_are_company_shared(self):
        """A gold rate is a fact about the market, not about a branch."""
        self.assertNotIn('company_id', self.Rate._fields)
