# -*- coding: utf-8 -*-
"""A compliance officer's decision to sell to a customer the screening blocked.

This is the part of the control that regulators actually read. It is therefore
the part with the fewest clever ideas in it: who, when, why, until when, and
no delete.

The override is held against the customer with an expiry rather than against
one order, for a counter reason. A false positive on a common name recurs on
every visit, and an override that had to be re-obtained per document would
either stop trade or train the manager to click through without reading. A
dated permission that lapses on its own is the honest middle.
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SamraAmlOverride(models.Model):
    _name = 'samra.aml.override'
    _description = 'AML Override'
    _order = 'create_date desc'
    _rec_name = 'partner_id'

    partner_id = fields.Many2one(
        'res.partner', required=True, ondelete='cascade', index=True)
    screening_id = fields.Many2one(
        'samra.aml.screening',
        help="The hit being overridden, so the decision can be read against "
             "what the provider actually said.")
    reason = fields.Text(
        required=True,
        help="Why this customer may be served despite the screening result.")
    user_id = fields.Many2one(
        'res.users', required=True, default=lambda self: self.env.user)
    valid_until = fields.Datetime(
        required=True,
        help="After this the block applies again without anyone having to "
             "remember to revoke it.")
    document = fields.Char(
        help="The order this was granted for, where it was granted from one.")
    active = fields.Boolean(default=True)

    @api.constrains('reason')
    def _check_reason(self):
        for override in self:
            if len((override.reason or '').strip()) < 15:
                raise ValidationError(_(
                    "The reason has to say something. An override with "
                    "'ok' written on it is worse than no override, because "
                    "it looks like a control."))

    @api.model
    def _live_for(self, partner):
        return self.sudo().search([
            ('partner_id', '=', partner.id),
            ('active', '=', True),
            ('valid_until', '>=', fields.Datetime.now()),
        ], limit=1)
