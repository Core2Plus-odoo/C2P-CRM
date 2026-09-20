# -*- coding: utf-8 -*-
"""The seam between this module and the RFID vendor's real hardware/API.

Duplicated in shape from samra_aml's and samra_planet's provider, and kept
independent of both for the same reason: three compliance/integration
workstreams that do not need each other should not become three that cannot
be installed without each other.
"""

import json
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30  # a full stock snapshot is a bigger payload than a screen


class SamraRfidProvider(models.Model):
    _name = 'samra.rfid.provider'
    _description = 'RFID Stock Sync Provider'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    provider_type = fields.Selection(
        [('rest', 'REST API'), ('manual', 'Manual (no call)')],
        required=True, default='manual',
        help="Manual pushes nothing anywhere. Each count line is left "
             "unscanned for a person to fill in, or a manager can simulate "
             "a scan for a demo -- see the push record's own button.")

    endpoint = fields.Char(help="Full URL the nightly stock snapshot is posted to.")
    auth_header = fields.Char(default='Authorization')
    auth_prefix = fields.Char(default='Bearer')
    api_key = fields.Char(
        string='Credential', groups='samra_rfid.group_rfid_manager')
    timeout = fields.Integer(default=DEFAULT_TIMEOUT)

    variance_tolerance = fields.Integer(
        default=0, required=True,
        help="A scanned count within this many units of the book quantity "
             "is not flagged. RFID reads are not always exact to the unit; "
             "flagging every rounding difference would make the list "
             "nobody's first read.")

    @api.constrains('endpoint', 'provider_type')
    def _check_endpoint(self):
        for provider in self:
            if provider.provider_type != 'rest':
                continue
            if not provider.endpoint:
                raise ValidationError(_("A REST provider needs an endpoint."))
            if not provider.endpoint.startswith(('http://', 'https://')):
                raise ValidationError(
                    _("The endpoint must be an http:// or https:// URL."))

    @api.constrains('timeout', 'variance_tolerance')
    def _check_positive(self):
        for provider in self:
            if provider.timeout <= 0:
                raise ValidationError(_("The timeout must be positive."))
            if provider.variance_tolerance < 0:
                raise ValidationError(_("The tolerance cannot be negative."))

    def push(self, lines):
        """Send today's snapshot. lines is a list of dicts with product_id,
        location_id, barcode and book_qty.

        Never raises: a vendor that is down overnight is a fact for the push
        record to carry, not an exception that stops the job before it has
        written anything.
        """
        self.ensure_one()
        payload = {'lines': lines}

        if self.provider_type == 'manual':
            return {'status': 'success',
                    'detail': _("Manual provider: nothing sent. Record "
                                "counts by hand, or simulate a scan."),
                    'request': json.dumps(payload), 'response': ''}

        headers = {'Content-Type': 'application/json'}
        key = self.sudo().api_key
        if key:
            headers[self.auth_header or 'Authorization'] = (
                f"{self.auth_prefix} {key}".strip() if self.auth_prefix else key)

        try:
            reply = requests.post(
                self.endpoint, json=payload, headers=headers,
                timeout=self.timeout or DEFAULT_TIMEOUT)
            reply.raise_for_status()
            return {'status': 'success', 'detail': '',
                    'request': json.dumps(payload)[:20000],
                    'response': json.dumps(reply.json())[:20000]}
        except requests.exceptions.Timeout:
            return self._failure(payload, _(
                "The RFID system did not answer within %s seconds.", self.timeout))
        except requests.exceptions.RequestException as error:
            return self._failure(payload, _(
                "The RFID system could not be reached: %s", error))
        except ValueError:
            return self._failure(payload, _(
                "The RFID system answered with something that is not JSON."))

    def _failure(self, payload, detail):
        _logger.warning("RFID push failed via %s: %s", self.name, detail)
        return {'status': 'error', 'detail': detail,
                'request': json.dumps(payload)[:20000], 'response': ''}

    @api.model
    def _active_provider(self):
        return self.search([('active', '=', True)], limit=1)
