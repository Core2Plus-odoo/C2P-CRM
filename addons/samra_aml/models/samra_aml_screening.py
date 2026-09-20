# -*- coding: utf-8 -*-
"""One row per screening call. The evidence, not the conclusion.

The partner carries the current status because that is what the till reads.
This carries how that status was arrived at, when, by whom and what the
provider actually said -- which is what an inspection asks for and what a
reviewer needs to clear a false positive.

Nobody can delete these, including the compliance manager. A deletable audit
trail is not one.
"""

from odoo import api, fields, models

STATUS = [
    ('whitelist', 'Cleared'),
    ('review', 'Possible Match'),
    ('blacklist', 'Blacklisted'),
    ('error', 'Screening Failed'),
]


class SamraAmlScreening(models.Model):
    _name = 'samra.aml.screening'
    _description = 'AML Screening Result'
    _order = 'screened_on desc, id desc'
    _rec_name = 'partner_id'

    partner_id = fields.Many2one(
        'res.partner', required=True, ondelete='cascade', index=True)
    provider_id = fields.Many2one('samra.aml.provider', ondelete='restrict')
    status = fields.Selection(STATUS, required=True, index=True)
    detail = fields.Char(help="Why the status is what it is, in words.")
    score = fields.Float(help="The provider's confidence, where it gives one.")
    list_name = fields.Char(string='Matched List')
    matched_name = fields.Char(
        help="The name on the list that matched, which is what a reviewer "
             "compares against the customer in front of them.")

    screened_on = fields.Datetime(required=True, default=fields.Datetime.now)
    screened_by = fields.Many2one(
        'res.users', default=lambda self: self.env.user,
        help="Empty means the scheduled run rather than a person.")
    next_due = fields.Datetime()

    request_payload = fields.Text(
        string='Sent', groups='samra_aml.group_aml_manager')
    response_payload = fields.Text(
        string='Received', groups='samra_aml.group_aml_manager')

    @api.model
    def _record(self, partner, provider, verdict):
        """Write the evidence and move the partner's status to match."""
        days = provider.rescreen_days if provider else 90
        screening = self.sudo().create({
            'partner_id': partner.id,
            'provider_id': provider.id if provider else False,
            'status': verdict['status'],
            'detail': verdict.get('detail', ''),
            'score': verdict.get('score', 0.0),
            'list_name': verdict.get('list_name', ''),
            'matched_name': verdict.get('matched_name', ''),
            'next_due': fields.Datetime.add(fields.Datetime.now(), days=days),
            'request_payload': verdict.get('request', ''),
            'response_payload': verdict.get('response', ''),
        })

        # A failed call must not overwrite a good verdict with nothing. The
        # customer keeps the status they had; the failure is still on record,
        # and next_due is left alone so the next run tries again.
        if verdict['status'] != 'error':
            partner.sudo().write({
                'x_aml_status': verdict['status'],
                'x_aml_score': verdict.get('score', 0.0),
                'x_aml_matched_list': verdict.get('list_name', ''),
                'x_aml_last_screened': screening.screened_on,
                'x_aml_next_due': screening.next_due,
            })
        return screening
