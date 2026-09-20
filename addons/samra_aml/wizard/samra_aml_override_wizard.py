# -*- coding: utf-8 -*-
"""Recording an override, with the reason mandatory at the point of decision.

A wizard rather than a button that writes a default: the reason has to be
typed by the person taking responsibility, while they are looking at the hit.
"""

from odoo import _, api, fields, models


class SamraAmlOverrideWizard(models.TransientModel):
    _name = 'samra.aml.override.wizard'
    _description = 'Record an AML Override'

    partner_id = fields.Many2one('res.partner', required=True, readonly=True)
    screening_id = fields.Many2one(
        'samra.aml.screening', string='Screening Result', readonly=True)
    status = fields.Selection(
        related='partner_id.x_aml_status', string='Current Status')
    matched_list = fields.Char(
        related='partner_id.x_aml_matched_list', string='Matched List')
    reason = fields.Text(
        required=True,
        help="What was checked, and why this customer is not the person on "
             "the list. This is read by whoever audits the decision.")
    valid_days = fields.Integer(
        string='Valid For (days)', default=1, required=True,
        help="Kept short on purpose. A standing permission is not an "
             "override, it is a policy change.")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        partner_id = values.get('partner_id') or self.env.context.get('default_partner_id')
        if partner_id and 'screening_id' in fields_list:
            last = self.env['samra.aml.screening'].search(
                [('partner_id', '=', partner_id)], limit=1)
            values['screening_id'] = last.id
        return values

    def action_record(self):
        self.ensure_one()
        override = self.env['samra.aml.override'].create({
            'partner_id': self.partner_id.id,
            'screening_id': self.screening_id.id,
            'reason': self.reason,
            'valid_until': fields.Datetime.add(
                fields.Datetime.now(), days=max(self.valid_days, 1)),
        })
        self.partner_id.message_post(body=_(
            "AML override recorded by %(user)s, valid until %(until)s: "
            "%(reason)s",
            user=self.env.user.display_name,
            until=override.valid_until,
            reason=self.reason,
        ))
        return {'type': 'ir.actions.act_window_close'}
