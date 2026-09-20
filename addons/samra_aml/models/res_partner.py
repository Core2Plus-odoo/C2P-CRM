# -*- coding: utf-8 -*-
"""The customer's screening status, and the one function the till calls.

Fields are x_-prefixed to match the convention the rest of this instance
already uses on res.partner.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .samra_aml_screening import STATUS

_logger = logging.getLogger(__name__)

NOT_SCREENED = 'not_screened'

# How many customers one scheduled run will screen. A vendor charges per call
# and rate-limits, and a run that tries the whole book on the first night will
# be throttled into failure and leave the batch half done.
BATCH = 200


class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_aml_status = fields.Selection(
        [(NOT_SCREENED, 'Not Screened')] + STATUS,
        string='AML Status', default=NOT_SCREENED, readonly=True, index=True,
        tracking=True,
        help="Set by screening. To change it by hand, screen again or record "
             "an override -- both of which leave a trail.")
    x_aml_score = fields.Float(string='Match Score', readonly=True)
    x_aml_matched_list = fields.Char(string='Matched List', readonly=True)
    x_aml_last_screened = fields.Datetime(readonly=True)
    x_aml_next_due = fields.Datetime(readonly=True)
    x_aml_screening_ids = fields.One2many(
        'samra.aml.screening', 'partner_id', string='Screening History')
    x_aml_override_ids = fields.One2many(
        'samra.aml.override', 'partner_id', string='Overrides')
    x_aml_blocked = fields.Boolean(
        compute='_compute_aml_blocked', string='AML Blocked',
        help="True when this customer cannot be sold to right now.")

    @api.depends('x_aml_status')
    def _compute_aml_blocked(self):
        for partner in self:
            partner.x_aml_blocked = partner.x_aml_status in ('blacklist', 'review')

    # -- screening -----------------------------------------------------

    def action_samra_aml_screen(self):
        """Screen these customers now. The manual path, for a person."""
        provider = self.env['samra.aml.provider']._active_provider()
        self._samra_aml_screen_with(provider)
        return True

    def _samra_aml_screen_with(self, provider):
        Screening = self.env['samra.aml.screening']
        for partner in self:
            verdict = provider.screen(partner)
            Screening._record(partner, provider, verdict)
        return True

    @api.model
    def _cron_samra_aml_rescreen(self):
        """Ongoing monitoring: lists change, customers do not.

        Picks up customers whose screening has lapsed AND customers who have
        never been screened, because on the first run after install nobody has
        a next_due and a query written only against expiry would screen
        nobody and look like it worked.
        """
        provider = self.env['samra.aml.provider'].search(
            [('active', '=', True)], limit=1)
        if not provider:
            _logger.info("Samra AML: no active provider, nothing screened.")
            return 0

        due = self.search([
            ('type', '=', 'contact'),
            '|',
            ('x_aml_next_due', '=', False),
            ('x_aml_next_due', '<=', fields.Datetime.now()),
        ], limit=BATCH, order='x_aml_next_due asc, id asc')

        if not due:
            _logger.info("Samra AML: nothing due for screening.")
            return 0

        due._samra_aml_screen_with(provider)
        _logger.info("Samra AML: screened %s customer(s) via %s",
                     len(due), provider.name)
        return len(due)

    # -- the control ---------------------------------------------------

    def _samra_aml_assert_sellable(self, document=None):
        """Raise if any of these customers may not be served.

        Called from the sale order and the POS. Not screened is deliberately
        not a block -- see the module description.
        """
        Override = self.env['samra.aml.override']
        for partner in self:
            if not partner.x_aml_blocked:
                continue

            override = Override._live_for(partner)
            if override:
                _logger.info(
                    "Samra AML: %s served on %s under override %s granted "
                    "by %s", partner.display_name, document or 'an unnamed document',
                    override.id, override.user_id.display_name)
                continue

            listed = _("is on %s", partner.x_aml_matched_list) \
                if partner.x_aml_matched_list else _("was flagged by screening")
            raise UserError(_(
                "%(customer)s cannot be served: AML screening says this "
                "customer %(listed)s (%(status)s).\n\n"
                "A compliance manager can record an override with a written "
                "reason from the customer's AML tab. Without one this sale "
                "cannot proceed.",
                customer=partner.display_name,
                listed=listed,
                status=dict(self._fields['x_aml_status'].selection).get(
                    partner.x_aml_status, partner.x_aml_status),
            ))

    def action_samra_aml_override(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Record AML Override"),
            'res_model': 'samra.aml.override.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_partner_id': self.id},
        }
