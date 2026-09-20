# -*- coding: utf-8 -*-
"""Tests weighted the way samra_aml's are: toward the behaviour that matters
rather than the plumbing. Here that is "a failure never blocks the sale" --
the opposite polarity from AML on purpose, and the one thing worth proving.
"""

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.samra_planet.models.samra_planet_provider import dig


def response(status='approved', tag='UAE-2026-PLN-1', vat=100.0):
    return {'status': status, 'tag_number': tag,
            'qr_code_string': f'https://planetpayment.ae/tf/{tag}',
            'refundable_vat': vat}


@tagged('post_install', '-at_install')
class PlanetCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env['samra.planet.provider'].create({
            'name': 'Test Provider', 'provider_type': 'rest',
            'endpoint': 'https://planet.example.com/issue',
            'merchant_id': 'SAMRA-TEST-01', 'status_path': 'status',
            'tag_path': 'tag_number', 'qr_path': 'qr_code_string',
            'refundable_vat_path': 'refundable_vat',
        })
        # The shipped default provider must not also be active, or a test
        # asserting "the active provider" could silently pick the wrong one.
        cls.env['samra.planet.provider'].search(
            [('id', '!=', cls.provider.id)]).write({'active': False})

        cls.tourist = cls.env['res.partner'].create({
            'name': 'John Smith', 'x_planet_is_tourist': True,
            'x_planet_passport_number': 'A98234110'})
        cls.local = cls.env['res.partner'].create({'name': 'Local Customer'})


@tagged('post_install', '-at_install')
class TestVerdictMapping(PlanetCase):

    def test_approved_is_recognised(self):
        result = self.provider._interpret({}, response('approved'))
        self.assertEqual(result['status'], 'approved')
        self.assertEqual(result['tag_number'], 'UAE-2026-PLN-1')

    def test_an_unrecognised_word_is_not_read_as_approved(self):
        """The failure that would matter: Planet returns a status this
        module has never seen, and it is read as a success anyway."""
        result = self.provider._interpret({}, response('under_review'))
        self.assertNotEqual(result['status'], 'approved')
        self.assertEqual(result['status'], 'declined')

    def test_dotted_paths_walk_nested_objects(self):
        body = {'shopper': {'status': 'approved'}}
        self.provider.status_path = 'shopper.status'
        result = self.provider._interpret({}, body)
        self.assertEqual(result['status'], 'approved')

    def test_a_missing_status_field_is_an_error_not_an_approval(self):
        result = self.provider._interpret({}, {'nothing': 'useful'})
        self.assertEqual(result['status'], 'error')


@tagged('post_install', '-at_install')
class TestAutomaticIssuance(PlanetCase):

    def _confirmed_order(self, partner):
        order = self.env['sale.order'].create({'partner_id': partner.id})
        order.action_confirm()
        return order

    def test_confirming_a_tourists_order_issues_a_tag(self):
        from unittest.mock import patch
        with patch.object(type(self.provider), 'issue',
                          return_value=response('approved', 'TAG-1')):
            order = self._confirmed_order(self.tourist)
        issuance = self.env['samra.planet.issuance'].search(
            [('order_ref', '=', order.name)])
        self.assertEqual(len(issuance), 1)
        self.assertEqual(issuance.tag_number, 'TAG-1')

    def test_a_local_customers_order_issues_nothing(self):
        order = self._confirmed_order(self.local)
        issuance = self.env['samra.planet.issuance'].search(
            [('order_ref', '=', order.name)])
        self.assertFalse(issuance)

    def test_a_provider_failure_does_not_block_the_sale(self):
        """The opposite polarity from AML, and the one thing worth proving:
        a tourist not getting a tag is corrected later, never a reason to
        refuse a paid, confirmed sale."""
        from unittest.mock import patch
        with patch.object(type(self.provider), 'issue',
                          return_value={'status': 'error', 'detail': 'timeout',
                                       'request': '', 'response': ''}):
            order = self._confirmed_order(self.tourist)
        self.assertEqual(order.state, 'sale')
        issuance = self.env['samra.planet.issuance'].search(
            [('order_ref', '=', order.name)])
        self.assertEqual(issuance.status, 'error')

    def test_no_active_provider_does_not_raise(self):
        self.provider.active = False
        order = self._confirmed_order(self.tourist)
        self.assertEqual(order.state, 'sale')


@tagged('post_install', '-at_install')
class TestWhoCanDoWhat(PlanetCase):

    def setUp(self):
        super().setUp()
        self.clerk = self.env['res.users'].create({
            'name': 'Counter Staff', 'login': 'planet_clerk_test',
            'group_ids': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('samra_planet.group_planet_user').id,
            ])],
        })

    def test_staff_cannot_read_the_merchant_token(self):
        self.provider.api_key = 'not-a-real-token'
        as_clerk = self.provider.with_user(self.clerk).read()[0]
        self.assertNotIn('api_key', as_clerk)
        as_manager = self.provider.read()[0]
        self.assertEqual(as_manager.get('api_key'), 'not-a-real-token')

    def test_nobody_deletes_an_issuance(self):
        issuance = self.env['samra.planet.issuance']._record(
            self._confirmed_order(self.tourist), self.provider, response())
        with self.assertRaises(AccessError):
            issuance.with_user(self.clerk).unlink()

    def _confirmed_order(self, partner):
        return self.env['sale.order'].create({'partner_id': partner.id})
