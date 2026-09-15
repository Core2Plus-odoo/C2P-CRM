# -*- coding: utf-8 -*-
"""Marketing consent, made enforceable rather than merely recorded.

Requirement 30 asks that consent be captured AND that customers be excludable
from campaigns. Capturing it was already done; the gap was that nothing stopped
a campaign from targeting someone who had declined. Under UAE PDPL that gap is
the part that matters -- a consent flag nobody consults is evidence of intent,
not compliance.

Enforcement here is at the point audiences are built, which is where the
decision is actually made. It deliberately does not monkey-patch Odoo's mailing
engine: a marketer who hand-writes a domain in Email Marketing can still reach
anyone, so this is a guard rail, not a seal. Closing that off properly means
wiring these domains into the mailing models, which needs a running instance to
do safely.
"""

from odoo import _, api, models

CHANNELS = {
    'whatsapp': 'x_whatsapp_consent',
    'sms': 'x_sms_consent',
}


class ResPartnerConsent(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _samra_consent_field(self, channel):
        try:
            return CHANNELS[channel]
        except KeyError:
            raise ValueError(
                f"Unknown marketing channel {channel!r}; "
                f"expected one of {', '.join(sorted(CHANNELS))}."
            )

    @api.model
    def _samra_marketing_domain(self, channel, base_domain=None):
        """Domain for a campaign audience on one channel.

        Consent is stored as a plain boolean, so an unset value reads as
        False -- which is the right default. Silence is not consent.
        """
        field = self._samra_consent_field(channel)
        return (base_domain or []) + [
            ('customer_rank', '>', 0),
            (field, '=', True),
        ]

    @api.model
    def samra_marketing_audience(self, channel, base_domain=None):
        """Consented recipients for a channel, with the excluded count.

        Returning what was excluded matters as much as returning the audience:
        a marketer who sees "412 reachable, 88 excluded" understands the shape
        of their consent problem. One that silently returns 412 does not.
        """
        domain = self._samra_marketing_domain(channel, base_domain)
        eligible = self.search(domain)
        everyone = self.search_count((base_domain or []) + [('customer_rank', '>', 0)])
        return {
            'channel': channel,
            'reachable': len(eligible),
            'excluded': everyone - len(eligible),
            'partner_ids': eligible.ids,
            'domain': domain,
        }

    def action_samra_whatsapp_audience(self):
        return self._samra_audience_action('whatsapp', _('WhatsApp Audience'))

    def action_samra_sms_audience(self):
        return self._samra_audience_action('sms', _('SMS Audience'))

    @api.model
    def _samra_audience_action(self, channel, name):
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'res.partner',
            'view_mode': 'list,form',
            'domain': self._samra_marketing_domain(channel),
            'context': {'create': False},
        }
