# -*- coding: utf-8 -*-
from datetime import date

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestProfileCurrencyConversion(TransactionCase):
    """An order placed in a currency other than the company's must be
    converted before it feeds the 360 profile or the lifetime-value cron --
    otherwise the figure is in one currency while the label next to it
    names another.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company_currency = cls.env.company.currency_id
        cls.foreign_currency = cls.env.ref('base.USD')
        if cls.foreign_currency == company_currency:
            cls.foreign_currency = cls.env.ref('base.EUR')
        cls.foreign_currency.active = True
        cls.env['res.currency.rate'].create({
            'currency_id': cls.foreign_currency.id,
            'name': date.today(),
            'rate': 3.6725,
            'company_id': cls.env.company.id,
        })

        cls.product = cls.env['product.product'].create(
            {'name': 'Currency Test Bangle', 'list_price': 1000.0, 'sale_ok': True})
        cls.customer = cls.env['res.partner'].create({'name': 'Currency Test Customer'})
        cls.order = cls.env['sale.order'].create({
            'partner_id': cls.customer.id,
            'currency_id': cls.foreign_currency.id,
            'order_line': [(0, 0, {'product_id': cls.product.id, 'product_uom_qty': 1})],
        })
        cls.order.action_confirm()

    def test_profile_order_amount_is_in_company_currency(self):
        order_row = self.customer._samra_orders()[0]
        expected = self.customer._samra_to_company_currency(self.order, self.order.amount_total)
        self.assertEqual(order_row['amount_total'], expected)
        self.assertNotEqual(
            order_row['amount_total'], self.order.amount_total,
            "a foreign-currency order shown under the company currency label "
            "must be converted, not passed through as-is")

    def test_analytics_revenue_is_in_company_currency(self):
        expected = self.customer._samra_to_company_currency(self.order, self.order.amount_total)
        analytics = self.customer._samra_analytics()
        self.assertAlmostEqual(analytics['lifetime_value'], expected, places=2)

    def test_lifetime_value_cron_converts_before_summing(self):
        expected = self.customer._samra_to_company_currency(self.order, self.order.amount_total)
        metrics = self.env['res.partner']._samra_purchase_metrics(self.customer)
        self.assertAlmostEqual(metrics[self.customer.id]['total'], expected, places=2)
