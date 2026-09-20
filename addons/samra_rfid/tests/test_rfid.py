# -*- coding: utf-8 -*-
"""Tests weighted towards the bug that would actually bite: confusing a
genuine scanned count of zero with a line nobody has scanned yet. That
distinction is the entire reason is_scanned exists as its own field rather
than reading rfid_qty's truthiness.
"""

from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class RfidCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env['samra.rfid.provider'].create({
            'name': 'Test Provider', 'provider_type': 'manual',
            'variance_tolerance': 1,
        })
        cls.env['samra.rfid.provider'].search(
            [('id', '!=', cls.provider.id)]).write({'active': False})


@tagged('post_install', '-at_install')
class TestVarianceLogic(RfidCase):

    def _line(self, book_qty):
        push = self.env['samra.rfid.push'].create(
            {'status': 'success', 'provider_id': self.provider.id, 'line_count': 1})
        product = self.env['product.product'].search([], limit=1)
        return self.env['samra.rfid.count'].create({
            'push_id': push.id, 'product_id': product.id, 'book_qty': book_qty,
        })

    def test_an_unscanned_line_has_no_variance(self):
        line = self._line(10)
        self.assertFalse(line.is_scanned)
        self.assertEqual(line.variance, 0.0)
        self.assertFalse(line.has_variance)

    def test_a_genuine_zero_scan_is_not_read_as_unscanned(self):
        """The bug this field split exists to prevent: book says 3, the scan
        genuinely finds none, and rfid_qty = 0.0 must not look identical to
        'nobody has scanned this yet'."""
        line = self._line(3)
        line.write({'rfid_qty': 0, 'is_scanned': True})
        self.assertTrue(line.is_scanned)
        self.assertEqual(line.variance, -3.0)
        self.assertTrue(line.has_variance)

    def test_typing_a_count_marks_the_line_scanned(self):
        line = self._line(5)
        line.rfid_qty = 5
        line._onchange_rfid_qty()
        self.assertTrue(line.is_scanned)

    def test_a_scan_matching_the_book_has_no_variance(self):
        line = self._line(5)
        line.write({'rfid_qty': 5, 'is_scanned': True})
        self.assertEqual(line.variance, 0.0)
        self.assertFalse(line.has_variance)

    def test_a_gap_within_tolerance_is_not_flagged(self):
        line = self._line(10)
        line.write({'rfid_qty': 9, 'is_scanned': True})  # tolerance is 1
        self.assertFalse(line.has_variance)

    def test_a_gap_beyond_tolerance_is_flagged(self):
        line = self._line(10)
        line.write({'rfid_qty': 7, 'is_scanned': True})
        self.assertTrue(line.has_variance)


@tagged('post_install', '-at_install')
class TestPush(RfidCase):

    def test_no_active_provider_does_not_raise(self):
        self.provider.active = False
        result = self.env['samra.rfid.push']._cron_samra_rfid_push()
        self.assertFalse(result)

    def test_a_push_creates_one_count_line_per_product_with_stock(self):
        product = self.env['product.product'].search(
            [('is_storable', '=', True)], limit=1)
        if not product:
            product = self.env['product.product'].create({
                'name': 'RFID Test Item', 'is_storable': True})
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        self.env['stock.quant']._update_available_quantity(
            product, warehouse.lot_stock_id, 12.0)

        push = self.env['samra.rfid.push']._samra_rfid_push_now(self.provider)
        self.assertEqual(push.status, 'success')
        line = push.count_ids.filtered(lambda l: l.product_id == product)
        self.assertTrue(line)
        self.assertEqual(line.book_qty, 12.0)

    def test_a_failed_push_is_still_recorded(self):
        with patch.object(type(self.provider), 'push',
                          return_value={'status': 'error', 'detail': 'timeout',
                                       'request': '', 'response': ''}):
            push = self.env['samra.rfid.push']._samra_rfid_push_now(self.provider)
        self.assertEqual(push.status, 'error')


@tagged('post_install', '-at_install')
class TestSimulateScan(RfidCase):

    def test_simulate_scan_only_touches_unscanned_lines(self):
        push = self.env['samra.rfid.push'].create(
            {'status': 'success', 'provider_id': self.provider.id, 'line_count': 2})
        product = self.env['product.product'].search([], limit=1)
        already = self.env['samra.rfid.count'].create({
            'push_id': push.id, 'product_id': product.id,
            'book_qty': 10, 'rfid_qty': 999, 'is_scanned': True,
        })
        untouched = self.env['samra.rfid.count'].create({
            'push_id': push.id, 'product_id': product.id, 'book_qty': 5,
        })

        push.action_simulate_scan()

        self.assertEqual(already.rfid_qty, 999,
                         "simulate overwrote a real scan result")
        self.assertTrue(untouched.is_scanned)
        self.assertGreaterEqual(untouched.rfid_qty, 0)

    def test_simulate_scan_never_writes_a_negative_count(self):
        push = self.env['samra.rfid.push'].create(
            {'status': 'success', 'provider_id': self.provider.id, 'line_count': 1})
        product = self.env['product.product'].search([], limit=1)
        line = self.env['samra.rfid.count'].create({
            'push_id': push.id, 'product_id': product.id, 'book_qty': 0,
        })
        for _i in range(20):  # the -2 delta only bites at low book quantities
            line.write({'is_scanned': False, 'rfid_qty': 0})
            push.action_simulate_scan()
            self.assertGreaterEqual(line.rfid_qty, 0)


@tagged('post_install', '-at_install')
class TestWhoCanDoWhat(RfidCase):

    def setUp(self):
        super().setUp()
        self.clerk = self.env['res.users'].create({
            'name': 'Warehouse Staff', 'login': 'rfid_clerk_test',
            'group_ids': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('samra_rfid.group_rfid_user').id,
            ])],
        })

    def test_staff_cannot_read_the_credential(self):
        self.provider.write({'provider_type': 'rest',
                             'endpoint': 'https://rfid.example.com/push',
                             'api_key': 'not-a-real-key'})
        as_clerk = self.provider.with_user(self.clerk).read()[0]
        self.assertNotIn('api_key', as_clerk)

    def test_staff_cannot_edit_a_provider(self):
        with self.assertRaises(AccessError):
            self.provider.with_user(self.clerk).write({'active': False})
