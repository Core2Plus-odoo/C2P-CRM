# -*- coding: utf-8 -*-
"""Tests weighted towards the control, not the plumbing.

The question that matters is not "does it parse JSON". It is "can a listed
customer be sold to". So most of this is about the refusal, the override, and
the cases where a vendor's answer is not one of the two words we expected.

No test makes a network call. The provider is stubbed by patching the one
method that does I/O, which is also why that method exists separately.
"""

from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.samra_aml.models.samra_aml_provider import dig


def answer(status='clear', score=0, list_name='', matched=''):
    """A vendor response in the shape the default mapping expects."""
    return {
        'status': status,
        'score': score,
        'match': {'list': list_name, 'name': matched},
    }


@tagged('post_install', '-at_install')
class AmlCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env['samra.aml.provider'].create({
            'name': 'Test Provider',
            'provider_type': 'rest',
            'endpoint': 'https://aml.example.com/screen',
            'api_key': 'not-a-real-key',
            'status_path': 'status',
            'score_path': 'score',
            'list_path': 'match.list',
            'matched_name_path': 'match.name',
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Aisha Rahman'})

    def screen_as(self, body, partner=None):
        """Screen one partner with a canned vendor response."""
        partner = partner or self.partner
        verdict = self.provider._interpret({'name': partner.name}, body)
        return self.env['samra.aml.screening']._record(
            partner, self.provider, verdict)


@tagged('post_install', '-at_install')
class TestVerdictMapping(AmlCase):

    def test_the_vendors_word_for_clear_clears(self):
        self.screen_as(answer('clear'))
        self.assertEqual(self.partner.x_aml_status, 'whitelist')
        self.assertFalse(self.partner.x_aml_blocked)

    def test_the_vendors_word_for_hit_blocks(self):
        self.screen_as(answer('hit', 98, 'UN Consolidated', 'A RAHMAN'))
        self.assertEqual(self.partner.x_aml_status, 'blacklist')
        self.assertEqual(self.partner.x_aml_matched_list, 'UN Consolidated')
        self.assertTrue(self.partner.x_aml_blocked)

    def test_a_word_we_do_not_know_is_not_assumed_to_be_clear(self):
        """The failure mode that would matter: a vendor says something new
        after an API change and every customer silently reads as cleared."""
        self.screen_as(answer('pending_manual_review'))
        self.assertEqual(self.partner.x_aml_status, 'review')
        self.assertTrue(self.partner.x_aml_blocked)

    def test_a_missing_status_field_is_not_assumed_to_be_clear(self):
        self.screen_as({'nothing': 'useful'})
        self.assertEqual(self.partner.x_aml_status, 'review')

    def test_the_mapping_is_configurable_per_vendor(self):
        self.provider.cleared_values = 'GREEN'
        self.provider.blocked_values = 'RED'
        self.screen_as(answer('RED'))
        self.assertEqual(self.partner.x_aml_status, 'blacklist')

    def test_dotted_paths_walk_lists(self):
        body = {'results': [{'status': 'hit'}]}
        self.assertEqual(dig(body, 'results.0.status'), 'hit')
        self.assertIsNone(dig(body, 'results.9.status'))
        self.assertIsNone(dig(body, 'results.0.missing'))


@tagged('post_install', '-at_install')
class TestFailureHandling(AmlCase):

    def test_a_failed_call_does_not_erase_a_good_verdict(self):
        """A vendor outage must not quietly clear a blacklisted customer, nor
        block the whole book by turning everyone into an error."""
        self.screen_as(answer('hit', 98, 'UN Consolidated'))
        self.assertEqual(self.partner.x_aml_status, 'blacklist')

        self.env['samra.aml.screening']._record(
            self.partner, self.provider,
            {'status': 'error', 'detail': 'timeout', 'request': '', 'response': ''})

        self.assertEqual(self.partner.x_aml_status, 'blacklist',
                         "an outage changed a customer's AML status")

    def test_a_failure_is_still_on_the_record(self):
        self.env['samra.aml.screening']._record(
            self.partner, self.provider,
            {'status': 'error', 'detail': 'timeout', 'request': '', 'response': ''})
        failures = self.env['samra.aml.screening'].search([
            ('partner_id', '=', self.partner.id), ('status', '=', 'error')])
        self.assertTrue(failures)


@tagged('post_install', '-at_install')
class TestTheControl(AmlCase):

    def setUp(self):
        super().setUp()
        self.order = self.env['sale.order'].create(
            {'partner_id': self.partner.id})

    def test_a_clear_customer_can_be_sold_to(self):
        self.screen_as(answer('clear'))
        self.order.action_confirm()
        self.assertEqual(self.order.state, 'sale')

    def test_a_listed_customer_cannot_be_sold_to(self):
        self.screen_as(answer('hit', 98, 'UN Consolidated', 'A RAHMAN'))
        with self.assertRaises(UserError) as caught:
            self.order.action_confirm()
        # Assert on the message: an order that fails to confirm for an
        # unrelated reason would otherwise pass this test and look like a
        # working control.
        self.assertIn('UN Consolidated', str(caught.exception))
        self.assertNotEqual(self.order.state, 'sale')

    def test_a_possible_match_also_stops_the_sale(self):
        self.screen_as(answer('unknown_word'))
        with self.assertRaises(UserError):
            self.order.action_confirm()

    def test_an_unscreened_customer_is_not_blocked(self):
        """Deliberate: screening runs on a schedule, so a walk-in served this
        morning has no status yet and refusing them would stop trade."""
        stranger = self.env['res.partner'].create({'name': 'Walk-in'})
        order = self.env['sale.order'].create({'partner_id': stranger.id})
        order.action_confirm()
        self.assertEqual(order.state, 'sale')

    def test_an_override_lets_the_sale_through(self):
        self.screen_as(answer('hit', 60, 'UN Consolidated', 'A RAHMAN'))
        self.env['samra.aml.override'].create({
            'partner_id': self.partner.id,
            'reason': 'Date of birth and passport differ from the listed person.',
            'valid_until': fields.Datetime.now() + timedelta(days=1),
        })
        self.order.action_confirm()
        self.assertEqual(self.order.state, 'sale')

    def test_an_expired_override_does_not(self):
        self.screen_as(answer('hit', 60, 'UN Consolidated'))
        self.env['samra.aml.override'].create({
            'partner_id': self.partner.id,
            'reason': 'Checked last month against the passport on file.',
            'valid_until': fields.Datetime.now() - timedelta(minutes=1),
        })
        with self.assertRaises(UserError):
            self.order.action_confirm()

    def test_an_override_needs_a_real_reason(self):
        with self.assertRaises(ValidationError):
            self.env['samra.aml.override'].create({
                'partner_id': self.partner.id,
                'reason': 'ok',
                'valid_until': fields.Datetime.now() + timedelta(days=1),
            })


@tagged('post_install', '-at_install')
class TestWhoCanDoWhat(AmlCase):

    def setUp(self):
        super().setUp()
        self.clerk = self.env['res.users'].create({
            'name': 'Counter Staff',
            'login': 'aml_clerk_test',
            'group_ids': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('samra_aml.group_aml_user').id,
            ])],
        })

    def test_staff_cannot_grant_themselves_an_override(self):
        self.screen_as(answer('hit', 98, 'UN Consolidated'))
        with self.assertRaises(AccessError):
            self.env['samra.aml.override'].with_user(self.clerk).create({
                'partner_id': self.partner.id,
                'reason': 'The customer seemed perfectly nice to me.',
                'valid_until': fields.Datetime.now() + timedelta(days=1),
            })

    def test_staff_cannot_read_the_credential(self):
        """Field-level groups, not just a hidden widget: the value must not
        come back through read() either.

        Reads every field the user is allowed, rather than naming one -- the
        first version of this test asked for ['name'] and then checked that
        'api_key' was absent, which it could not help but be."""
        as_clerk = self.provider.with_user(self.clerk).read()[0]
        self.assertNotIn('api_key', as_clerk)

        as_manager = self.provider.read()[0]
        self.assertEqual(as_manager.get('api_key'), 'not-a-real-key',
                         "the restriction is meaningless if nobody can read it")

    def test_nobody_deletes_the_evidence(self):
        screening = self.screen_as(answer('hit', 98, 'UN Consolidated'))
        with self.assertRaises(AccessError):
            screening.with_user(self.clerk).unlink()


@tagged('post_install', '-at_install')
class TestScheduledRun(AmlCase):

    def test_the_first_run_screens_customers_who_have_no_status(self):
        """A query written only against expiry screens nobody on day one, and
        looks like it worked."""
        fresh = self.env['res.partner'].create({'name': 'Never Screened'})
        self.assertFalse(fresh.x_aml_next_due)

        with patch.object(type(self.provider), 'screen',
                          return_value={'status': 'whitelist', 'detail': '',
                                        'request': '', 'response': ''}):
            count = self.env['res.partner']._cron_samra_aml_rescreen()

        self.assertTrue(count)
        self.assertEqual(fresh.x_aml_status, 'whitelist')

    def test_a_customer_screened_yesterday_is_left_alone(self):
        self.screen_as(answer('clear'))
        due = self.partner.x_aml_next_due
        self.assertGreater(due, fields.Datetime.now())

        with patch.object(type(self.provider), 'screen',
                          return_value={'status': 'blacklist', 'detail': '',
                                        'request': '', 'response': ''}):
            self.env['res.partner']._cron_samra_aml_rescreen()

        self.assertEqual(self.partner.x_aml_status, 'whitelist',
                         "a customer still in date was re-screened anyway")

    def test_no_active_provider_is_not_an_exception(self):
        self.provider.active = False
        self.env['samra.aml.provider'].search([]).write({'active': False})
        self.assertEqual(self.env['res.partner']._cron_samra_aml_rescreen(), 0)


@tagged('post_install', '-at_install')
class TestTheTill(AmlCase):
    """The POS check runs server-side in _process_order, before the order is
    created, so these call it directly with a deliberately invalid session:
    if the AML refusal comes back, it fired before anything else could."""

    def test_the_till_refuses_a_listed_customer(self):
        self.screen_as(answer('hit', 98, 'UN Consolidated', 'A RAHMAN'))
        with self.assertRaises(UserError) as caught:
            self.env['pos.order']._process_order(
                {'partner_id': self.partner.id, 'session_id': 0}, False)
        self.assertIn('UN Consolidated', str(caught.exception))

    def test_the_till_does_not_refuse_a_cleared_customer(self):
        """The counterpart: the same call must fail on the bogus session
        rather than on AML, or the test above proves nothing."""
        self.screen_as(answer('clear'))
        with self.assertRaises(Exception) as caught:
            self.env['pos.order']._process_order(
                {'partner_id': self.partner.id, 'session_id': 0}, False)
        self.assertNotIn('AML screening', str(caught.exception))


@tagged('post_install', '-at_install')
class TestTheDossier(AmlCase):
    """The 360 reads AML through a guard, so it must work with the module
    present and be absent-safe without it. Only the first half is testable
    here; the second is what the guard is for."""

    def test_the_dossier_carries_the_current_status(self):
        self.screen_as(answer('hit', 98, 'UN Consolidated', 'A RAHMAN'))
        aml = self.partner.get_samra_profile()['aml']
        self.assertEqual(aml['status'], 'blacklist')
        self.assertTrue(aml['blocked'])

    def test_a_cleared_customer_still_reports_a_status(self):
        """Absent would read as 'not checked', which is the opposite of what
        a cleared screening means."""
        self.screen_as(answer('clear'))
        aml = self.partner.get_samra_profile()['aml']
        self.assertEqual(aml['status'], 'whitelist')
        self.assertFalse(aml['blocked'])

    def test_the_dossier_carries_only_the_status(self):
        """The detail belongs on the AML tab. Asserted rather than left to
        drift, because a payload quietly regrowing fields is how a screen
        ends up showing what somebody asked it not to."""
        self.screen_as(answer('hit', 98, 'UN Consolidated', 'A RAHMAN'))
        aml = self.partner.get_samra_profile()['aml']
        self.assertEqual(set(aml), {'status', 'label', 'blocked'})
