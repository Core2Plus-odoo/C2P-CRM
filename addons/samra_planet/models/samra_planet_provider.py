# -*- coding: utf-8 -*-
"""The seam between this module and Planet Payment's real API.

Duplicated from samra_aml's provider rather than shared, deliberately: the two
compliance modules stay independent of each other, the way the flow engine's
own STUDIO_MODELS work stays independent of the CRM dashboard. A shared base
class would couple two things that have no reason to change together, to save
under a hundred lines that are simple enough to not be worth the coupling.
"""

import json
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20


def dig(payload, path):
    """Read a dotted path out of a decoded JSON body. See samra_aml.provider."""
    if not path:
        return None
    current = payload
    for step in path.split('.'):
        if isinstance(current, list):
            try:
                current = current[int(step)]
            except (ValueError, IndexError):
                return None
        elif isinstance(current, dict):
            if step not in current:
                return None
            current = current[step]
        else:
            return None
    return current


class SamraPlanetProvider(models.Model):
    _name = 'samra.planet.provider'
    _description = 'Planet Tax-Free Provider'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    provider_type = fields.Selection(
        [('rest', 'REST API'), ('manual', 'Manual (no call)')],
        required=True, default='manual',
        help="Manual records a tag by hand -- the correct default until "
             "Planet's real API contract has been confirmed against a "
             "sample from them, not from a meeting summary.")

    endpoint = fields.Char(
        help="Full URL of Planet's tax-free issuance endpoint.")
    merchant_id = fields.Char(
        help="This boutique's merchant identifier with Planet, e.g. "
             "SAMRA-DUBAI-HILL-01.")
    auth_header = fields.Char(default='Authorization')
    auth_prefix = fields.Char(default='Bearer')
    api_key = fields.Char(
        string='Merchant Token', groups='samra_planet.group_planet_manager',
        help="Never logged.")
    timeout = fields.Integer(default=DEFAULT_TIMEOUT)

    status_path = fields.Char(default='status')
    tag_path = fields.Char(default='tag_number')
    qr_path = fields.Char(default='qr_code_string')
    refundable_vat_path = fields.Char(default='refundable_vat')

    approved_values = fields.Char(
        default='approved,success,issued', required=True,
        help="Comma-separated values from Planet that mean the tag was "
             "issued. Anything else is treated as declined -- it is a tax "
             "document, so an unrecognised answer is not read as a success.")

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

    @api.constrains('timeout')
    def _check_positive(self):
        for provider in self:
            if provider.timeout <= 0:
                raise ValidationError(_("The timeout must be positive."))

    def _subject(self, order):
        """What Planet needs to issue a tag: the shopper and the sale total.

        Field names follow the MoM's sample payload for now, which is the
        only shape available. Treat every one of these as provisional --
        this is exactly what a real sample from Planet is for confirming.
        """
        self.ensure_one()
        partner = order.partner_id
        parts = (partner.name or '').split(' ', 1)
        first_name, last_name = parts[0], (parts[1] if len(parts) > 1 else '')
        return {
            'merchant_id': self.merchant_id or '',
            'invoice_number': order.name,
            'shopper_details': {
                'first_name': first_name,
                'last_name': last_name,
                'passport_number': partner.x_planet_passport_number or '',
                'country': partner.country_id.code or '',
            },
            'purchase_summary': {
                'gross_amount': order.amount_total,
                'vat_amount': order.amount_tax,
                'currency': order.currency_id.name or 'AED',
            },
        }

    def issue(self, order):
        """Return a normalised result. Never raises.

        A tourist not getting a tag immediately is corrected later by hand;
        it is never a reason to hold up a confirmed, paid sale.
        """
        self.ensure_one()
        subject = self._subject(order)

        if self.provider_type == 'manual':
            return {
                'status': 'pending',
                'detail': _("Manual provider: record the tag by hand once "
                            "Planet issues it."),
                'request': json.dumps(subject),
                'response': '',
            }

        headers = {'Content-Type': 'application/json'}
        key = self.sudo().api_key
        if key:
            headers[self.auth_header or 'Authorization'] = (
                f"{self.auth_prefix} {key}".strip() if self.auth_prefix else key)

        try:
            reply = requests.post(
                self.endpoint, json=subject, headers=headers,
                timeout=self.timeout or DEFAULT_TIMEOUT)
            reply.raise_for_status()
            body = reply.json()
        except requests.exceptions.Timeout:
            return self._failure(subject, _(
                "Planet did not answer within %s seconds.", self.timeout))
        except requests.exceptions.RequestException as error:
            return self._failure(subject, _(
                "Planet could not be reached: %s", error))
        except ValueError:
            return self._failure(subject, _(
                "Planet answered with something that is not JSON."))

        return self._interpret(subject, body)

    def _failure(self, subject, detail):
        _logger.warning("Planet tax-free issuance failed via %s: %s", self.name, detail)
        return {'status': 'error', 'detail': detail,
                'request': json.dumps(subject), 'response': ''}

    def _interpret(self, subject, body):
        self.ensure_one()
        raw = dig(body, self.status_path)
        token = str(raw).strip().lower() if raw is not None else ''
        approved = {v.strip().lower() for v in (self.approved_values or '').split(',') if v.strip()}

        if token in approved:
            status, detail = 'approved', _("Planet issued a tax-free tag.")
        elif not token:
            status = 'error'
            detail = _("No value at '%s' in Planet's response.", self.status_path)
        else:
            status, detail = 'declined', _("Planet declined: %s", token)

        vat = dig(body, self.refundable_vat_path)
        try:
            vat = float(vat) if vat is not None else 0.0
        except (TypeError, ValueError):
            vat = 0.0

        return {
            'status': status,
            'detail': detail,
            'tag_number': dig(body, self.tag_path) or '',
            'qr_code_string': dig(body, self.qr_path) or '',
            'refundable_vat': vat,
            'request': json.dumps(subject),
            'response': json.dumps(body)[:20000],
        }

    @api.model
    def _active_provider(self):
        return self.search([('active', '=', True)], limit=1)
