# -*- coding: utf-8 -*-
"""The nightly snapshot, and the per-product comparison it exists to produce.

A push with nothing worth reading is the common case, and the point of the
gap analysis is to make the rare push that isn't look different at a glance
-- not to make every push a report someone has to read line by line.
"""

import logging
import random

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

STATUS = [('success', 'Sent'), ('error', 'Failed')]

# Bulk-loading a whole boutique's stock into one push keeps a night's run to
# one request instead of one per product; a vendor with a smaller payload
# limit is a reason to page this, not a reason every push should.
BATCH_LIMIT = 5000


class SamraRfidPush(models.Model):
    _name = 'samra.rfid.push'
    _description = 'RFID Stock Push'
    _order = 'push_date desc'

    push_date = fields.Datetime(required=True, default=fields.Datetime.now)
    provider_id = fields.Many2one('samra.rfid.provider', ondelete='restrict')
    status = fields.Selection(STATUS, required=True)
    detail = fields.Char()
    line_count = fields.Integer(string='Products Pushed')
    variance_count = fields.Integer(
        compute='_compute_variance_count', string='Lines With a Gap')

    count_ids = fields.One2many('samra.rfid.count', 'push_id', string='Comparison')

    request_payload = fields.Text(
        string='Sent', groups='samra_rfid.group_rfid_manager')
    response_payload = fields.Text(
        string='Received', groups='samra_rfid.group_rfid_manager')

    @api.depends('count_ids.has_variance')
    def _compute_variance_count(self):
        for push in self:
            push.variance_count = len(push.count_ids.filtered('has_variance'))

    # -- building and sending the snapshot -------------------------------

    def _samra_rfid_snapshot(self):
        """One line per product with stock on hand in an internal location.

        Grouped rather than per-quant: two shelves of the same ring are one
        line to the RFID system's own stock model, and pushing per-quant
        would double-count a product split across bins for no reason a
        vendor's API would want.
        """
        quants = self.env['stock.quant']._read_group(
            [('location_id.usage', '=', 'internal'), ('quantity', '>', 0)],
            ['product_id'], ['quantity:sum'],
        )
        return [{
            'product_id': product.id,
            'barcode': product.barcode or product.default_code or '',
            'book_qty': qty,
        } for product, qty in quants]

    @api.model
    def _cron_samra_rfid_push(self):
        provider = self.env['samra.rfid.provider']._active_provider()
        if not provider:
            _logger.info("Samra RFID: no active provider, nothing pushed.")
            return False
        return self._samra_rfid_push_now(provider)

    @api.model
    def _samra_rfid_push_now(self, provider):
        lines = self._samra_rfid_snapshot()
        result = provider.push(lines[:BATCH_LIMIT])

        push = self.sudo().create({
            'push_date': fields.Datetime.now(),
            'provider_id': provider.id,
            'status': result['status'],
            'detail': result.get('detail', ''),
            'line_count': len(lines),
            'request_payload': result.get('request', ''),
            'response_payload': result.get('response', ''),
        })

        Count = self.env['samra.rfid.count'].sudo()
        Count.create([{
            'push_id': push.id,
            'product_id': line['product_id'],
            'book_qty': line['book_qty'],
        } for line in lines])

        _logger.info("Samra RFID: pushed %s product line(s) via %s (%s)",
                     len(lines), provider.name, result['status'])
        return push

    # -- demo convenience --------------------------------------------------

    def action_simulate_scan(self):
        """Fill in unscanned lines with a plausible small variance.

        This is explicitly a stand-in for the vendor's real overnight scan,
        which this instance does not have yet. It touches only lines with no
        rfid_qty recorded, so it never overwrites a real scan result once one
        exists.
        """
        self.ensure_one()
        rng = random.Random()
        pending = self.count_ids.filtered(lambda line: not line.is_scanned)
        for line in pending:
            # Mostly exact, occasionally off by a small amount -- a scan that
            # never disagrees with the book would make the gap list pointless
            # to demonstrate.
            delta = rng.choice([0, 0, 0, 0, -1, 1, -2, 2])
            line.write({
                'rfid_qty': max(line.book_qty + delta, 0),
                'is_scanned': True,
            })
        return True


class SamraRfidCount(models.Model):
    _name = 'samra.rfid.count'
    _description = 'RFID Stock Count Line'
    _order = 'has_variance desc, id'

    push_id = fields.Many2one(
        'samra.rfid.push', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', required=True, index=True)
    book_qty = fields.Float(string='Book Quantity', required=True)
    rfid_qty = fields.Float(string='Scanned Quantity')
    is_scanned = fields.Boolean(
        string='Scanned', default=False,
        help="False until the vendor's scan result, or a manual count, is "
             "recorded against this line. Separate from rfid_qty because a "
             "genuine scanned count of zero must not read as 'not scanned'.")
    variance = fields.Float(compute='_compute_variance', store=True)
    has_variance = fields.Boolean(compute='_compute_variance', store=True)

    @api.onchange('rfid_qty')
    def _onchange_rfid_qty(self):
        # A count typed by hand in the editable list is a scan result the
        # moment somebody types it -- there is no separate "confirm" step,
        # so the flag has to follow the field it is disambiguating.
        for line in self:
            if not line.is_scanned:
                line.is_scanned = True

    @api.depends('rfid_qty', 'is_scanned', 'book_qty',
                 'push_id.provider_id.variance_tolerance')
    def _compute_variance(self):
        for line in self:
            if not line.is_scanned:
                line.variance = 0.0
                line.has_variance = False
                continue
            tolerance = line.push_id.provider_id.variance_tolerance or 0
            line.variance = line.rfid_qty - line.book_qty
            line.has_variance = abs(line.variance) > tolerance
