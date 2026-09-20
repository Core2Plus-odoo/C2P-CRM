# -*- coding: utf-8 -*-
"""The seam between this module and whichever AML software the firm bought.

Every vendor in this market returns the same three ideas -- is there a match,
how good a match, which list -- under different names, in a different shape,
with a different word for "clear". So the adapter is configuration: paths into
the response, and an explicit mapping from the vendor's vocabulary onto ours.

The mapping is deliberately not clever. There is no fuzzy matching of status
words, no "if it contains 'clear' it is probably fine". A value that is not
listed as meaning cleared, and not listed as meaning blocked, becomes Possible
Match -- which blocks and asks for a human. Guessing in that direction is the
only safe way to be wrong.
"""

import json
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# A screening call is on the path of a nightly batch, not a user click, but a
# vendor that hangs must not hold the cron open all night.
DEFAULT_TIMEOUT = 20


def dig(payload, path):
    """Read a dotted path out of a decoded JSON body.

    'results.0.match.status' walks dicts by key and lists by index. Returns
    None rather than raising: a missing field is a fact about the response,
    and the caller turns it into a status.
    """
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


class SamraAmlProvider(models.Model):
    _name = 'samra.aml.provider'
    _description = 'AML Screening Provider'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    provider_type = fields.Selection(
        [('rest', 'REST API'), ('manual', 'Manual (no call)')],
        required=True, default='rest',
        help="Manual exists so the control can go live before the vendor is "
             "wired: a compliance officer sets each status by hand and "
             "everything downstream behaves identically.")

    endpoint = fields.Char(
        help="Full URL of the screening endpoint, e.g. "
             "https://aml.example.com/api/v2/screen")
    auth_header = fields.Char(
        default='Authorization',
        help="Header the credential is sent in. Some vendors want "
             "'X-API-Key' rather than 'Authorization'.")
    auth_prefix = fields.Char(
        default='Bearer',
        help="Word placed before the credential, if the vendor wants one.")
    # Field-level groups: the ORM refuses to read or write this for anyone
    # outside the group, so it does not reach a list view, an export or the
    # web client for ordinary staff.
    api_key = fields.Char(
        string='Credential', groups='samra_aml.group_aml_manager',
        help="Never logged. Stored on this record so it can be rotated "
             "without a deployment.")
    timeout = fields.Integer(default=DEFAULT_TIMEOUT)

    # -- response mapping ----------------------------------------------
    status_path = fields.Char(
        default='status',
        help="Dotted path to the verdict in the response body. List indexes "
             "are allowed: results.0.status")
    score_path = fields.Char(help="Dotted path to a match score, if any.")
    list_path = fields.Char(
        help="Dotted path to the name of the list matched, e.g. 'UN "
             "Consolidated' or 'UAE Local Terrorist List'.")
    matched_name_path = fields.Char(
        help="Dotted path to the name that matched, which is what a reviewer "
             "actually needs to see to clear a false positive.")

    cleared_values = fields.Char(
        default='clear,clean,no_match,whitelisted,ok',
        required=True,
        help="Comma-separated values from the vendor that mean NOT listed.")
    blocked_values = fields.Char(
        default='hit,match,blacklisted,listed,sanctioned',
        required=True,
        help="Comma-separated values from the vendor that mean listed. "
             "Anything matching neither list becomes Possible Match, which "
             "blocks and asks for a human.")

    rescreen_days = fields.Integer(
        default=90, required=True,
        help="How long a screening stays good for. After this the customer "
             "is picked up by the next scheduled run.")

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
            if provider.endpoint.startswith('http://'):
                _logger.warning(
                    "AML provider %s posts customer identity data over plain "
                    "HTTP. Use https unless the endpoint is on the local "
                    "network.", provider.name)

    @api.constrains('timeout', 'rescreen_days')
    def _check_positive(self):
        for provider in self:
            if provider.timeout <= 0:
                raise ValidationError(_("The timeout must be positive."))
            if provider.rescreen_days <= 0:
                raise ValidationError(_("Re-screening must be at least a day."))

    # -- the call ------------------------------------------------------

    def _subject(self, partner):
        """What we send. Deliberately the minimum that identifies a person.

        Screening is the one place a jeweller's customer list leaves the
        building, so this sends what the match needs and nothing more -- no
        purchase history, no spend, no contact preferences.
        """
        self.ensure_one()
        return {
            'name': partner.name or '',
            'country': partner.country_id.code or '',
            'reference': f'res.partner:{partner.id}',
        }

    def screen(self, partner):
        """Return a normalised verdict for one partner.

        Never raises. A vendor that is down, slow or returning nonsense is an
        operational fact to be recorded, not an exception that kills the
        nightly batch half way through the customer book.
        """
        self.ensure_one()
        subject = self._subject(partner)

        if self.provider_type == 'manual':
            return {
                'status': 'review',
                'detail': "Manual provider: a compliance officer sets this "
                          "status by hand.",
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
                "The provider did not answer within %s seconds.", self.timeout))
        except requests.exceptions.RequestException as error:
            # str(error) can carry the URL but never the header we set.
            return self._failure(subject, _(
                "The provider could not be reached: %s", error))
        except ValueError:
            return self._failure(subject, _(
                "The provider answered with something that is not JSON."))

        return self._interpret(subject, body)

    def _failure(self, subject, detail):
        _logger.warning("AML screening failed via %s: %s", self.name, detail)
        return {
            'status': 'error',
            'detail': detail,
            'request': json.dumps(subject),
            'response': '',
        }

    def _interpret(self, subject, body):
        self.ensure_one()
        raw = dig(body, self.status_path)
        token = str(raw).strip().lower() if raw is not None else ''

        cleared = {v.strip().lower() for v in (self.cleared_values or '').split(',') if v.strip()}
        blocked = {v.strip().lower() for v in (self.blocked_values or '').split(',') if v.strip()}

        if token in blocked:
            status = 'blacklist'
            detail = _("The provider reported a match.")
        elif token in cleared:
            status = 'whitelist'
            detail = _("The provider reported no match.")
        elif not token:
            status = 'review'
            detail = _(
                "No value at '%s' in the response. Check the provider's "
                "response mapping.", self.status_path)
        else:
            status = 'review'
            detail = _(
                "The provider said '%s', which is mapped to neither cleared "
                "nor blocked. Treated as a possible match until somebody "
                "decides which it is.", token)

        score = dig(body, self.score_path)
        try:
            score = float(score) if score is not None else 0.0
        except (TypeError, ValueError):
            score = 0.0

        return {
            'status': status,
            'detail': detail,
            'score': score,
            'list_name': dig(body, self.list_path) or '',
            'matched_name': dig(body, self.matched_name_path) or '',
            'request': json.dumps(subject),
            'response': json.dumps(body)[:20000],
        }

    @api.model
    def _active_provider(self):
        provider = self.search([('active', '=', True)], limit=1)
        if not provider:
            raise UserError(_(
                "No AML provider is configured. Set one up under "
                "Contacts > Configuration > AML Screening."))
        return provider
