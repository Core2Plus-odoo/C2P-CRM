# -*- coding: utf-8 -*-
"""One row per tax-free tag issued, or attempted.

Kept for the same reason samra.aml.screening is kept: it is a fiscal document
Samra is accountable for at audit, not just a UI convenience, so nobody --
including a manager -- can delete it.

Deliberately not linked back to sale.order or pos.order by a foreign key.
The two are unrelated models -- a POS sale does not create a sale.order --
and a polymorphic reference would buy nothing a plain order reference number
does not, for a record that exists to be read, not navigated from.
"""

from odoo import api, fields, models

STATUS = [
    ('pending', 'Pending'),
    ('approved', 'Approved'),
    ('declined', 'Declined'),
    ('error', 'Failed'),
]


class SamraPlanetIssuance(models.Model):
    _name = 'samra.planet.issuance'
    _description = 'Planet Tax-Free Issuance'
    _order = 'create_date desc'
    _rec_name = 'order_ref'

    partner_id = fields.Many2one(
        'res.partner', required=True, ondelete='cascade', index=True)
    order_ref = fields.Char(
        string='Order', required=True,
        help="The sale or POS order this tag was issued for.")
    provider_id = fields.Many2one('samra.planet.provider', ondelete='restrict')
    status = fields.Selection(STATUS, required=True, default='pending', index=True)
    detail = fields.Char()

    tag_number = fields.Char()
    qr_code_string = fields.Char()
    refundable_vat = fields.Monetary(currency_field='currency_id')
    currency_id = fields.Many2one('res.currency')

    request_payload = fields.Text(
        string='Sent', groups='samra_planet.group_planet_manager')
    response_payload = fields.Text(
        string='Received', groups='samra_planet.group_planet_manager')

    @api.model
    def _record(self, order, provider, result):
        """order is a sale.order or a pos.order -- anything exposing name,
        partner_id and currency_id, which both do."""
        return self.sudo().create({
            'partner_id': order.partner_id.id,
            'order_ref': order.name,
            'currency_id': order.currency_id.id if order.currency_id else False,
            'provider_id': provider.id if provider else False,
            'status': result['status'],
            'detail': result.get('detail', ''),
            'tag_number': result.get('tag_number', ''),
            'qr_code_string': result.get('qr_code_string', ''),
            'refundable_vat': result.get('refundable_vat', 0.0),
            'request_payload': result.get('request', ''),
            'response_payload': result.get('response', ''),
        })
