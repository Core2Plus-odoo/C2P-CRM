# -*- coding: utf-8 -*-
"""Upcoming birthdays and anniversaries, as something you can actually work.

Requirement 17 asks for birthday tracking. The dates were already captured --
x_birthday and x_anniversary have existed since the first version -- but a
stored date of birth is not a clienteling tool. Nobody can answer "who should
I call this week?" from it, because the question is about the anniversary of a
date, not the date, and SQL has no comparison for that.

So the recurring dates are projected forward into real ones. x_birthday_next
and x_anniversary_next hold the next time each occasion actually falls, as
ordinary Date columns. Everything a list view needs then works for free:
ordering, grouping, a date filter, a domain handed to an act_window.

The projection depends on today as well as on the stored date, and Odoo has no
way to express "recompute when the calendar turns". That is what the nightly
cron is for: it already walks every customer to refresh purchase metrics, so
it marks these for recomputation on the same pass. Between runs a date that
has just passed reads as up to one day stale, which for a list of people to
phone this month is not a problem worth a heavier mechanism.

29 February is handled by falling back to the 28th in common years. The
alternative -- 1 March -- moves the occasion into the wrong month, which is
exactly the month boundary the whole feature is organised around.
"""

import logging
from datetime import date, timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# How far ahead the Upcoming Occasions view looks by default.
HORIZON_DAYS = 30

# Plain strings, translated where they are read. A _() call at import time is
# evaluated before any user context exists, so it would freeze the English.
OCCASION_LABELS = {
    'birthday': 'Birthday',
    'anniversary': 'Anniversary',
}


def _next_occurrence(when, today):
    """The next time this day-and-month falls on or after today."""
    if not when:
        return False

    def _on(year):
        try:
            return date(year, when.month, when.day)
        except ValueError:
            # 29 February in a common year. Keep it in February.
            return date(year, 2, 28)

    this_year = _on(today.year)
    return this_year if this_year >= today else _on(today.year + 1)


class ResPartnerOccasions(models.Model):
    _inherit = 'res.partner'

    x_birthday_next = fields.Date(
        string='Next Birthday', compute='_compute_samra_occasions', store=True,
        help='The next time this birthday falls. Refreshed nightly.')
    x_anniversary_next = fields.Date(
        string='Next Anniversary', compute='_compute_samra_occasions', store=True)

    x_next_occasion_date = fields.Date(
        string='Next Occasion', compute='_compute_samra_occasions', store=True,
        help='Whichever of the birthday or anniversary comes first.')
    x_next_occasion_type = fields.Selection(
        [('birthday', 'Birthday'), ('anniversary', 'Anniversary')],
        string='Occasion', compute='_compute_samra_occasions', store=True)
    x_days_to_occasion = fields.Integer(
        string='Days Away', compute='_compute_samra_occasions', store=True)

    # Counted rather than stored: the wishlist is small per customer and a
    # stored count would need invalidating from three other models.
    #
    # compute_sudo because this is a column in a partner list. An AccessError
    # raised while rendering a list is a broken screen, not a permission
    # prompt, and the figure leaks nothing a viewer of the customer is not
    # already entitled to -- how many pieces they have wishlisted, not which.
    x_wishlist_count = fields.Integer(
        string='Wishlist', compute='_compute_samra_wishlist_count',
        compute_sudo=True)
    x_wishlist_value = fields.Float(
        string='Wishlist Value', compute='_compute_samra_wishlist_count',
        compute_sudo=True)

    def _compute_samra_wishlist_count(self):
        counts = dict(self.env['x_samra_wishlist']._read_group(
            [('x_partner_id', 'in', self.ids)], ['x_partner_id'], ['__count']))
        values = dict(self.env['x_samra_wishlist']._read_group(
            [('x_partner_id', 'in', self.ids)], ['x_partner_id'], ['x_price:sum']))
        for partner in self:
            partner.x_wishlist_count = counts.get(partner, 0)
            partner.x_wishlist_value = values.get(partner, 0.0)

    @api.depends('x_birthday', 'x_anniversary')
    def _compute_samra_occasions(self):
        today = fields.Date.context_today(self)
        for partner in self:
            birthday = _next_occurrence(partner.x_birthday, today)
            anniversary = _next_occurrence(partner.x_anniversary, today)

            partner.x_birthday_next = birthday
            partner.x_anniversary_next = anniversary

            candidates = [c for c in (
                ('birthday', birthday), ('anniversary', anniversary)) if c[1]]
            if not candidates:
                partner.x_next_occasion_date = False
                partner.x_next_occasion_type = False
                partner.x_days_to_occasion = 0
                continue

            # Birthday first on a tie -- it is the one the customer expects
            # to be remembered, and a shared date is almost always a
            # coincidence rather than a second event worth two messages.
            kind, when = min(candidates, key=lambda c: (c[1], c[0] != 'birthday'))
            partner.x_next_occasion_date = when
            partner.x_next_occasion_type = kind
            partner.x_days_to_occasion = (when - today).days

    # ------------------------------------------------------------------
    # Keeping them current
    # ------------------------------------------------------------------

    def _samra_refresh_occasions(self):
        """Re-project the recurring dates against today.

        Called from the nightly metrics cron. Without it every projection
        would freeze at whatever today was when the date was last edited.
        """
        for name in ('x_birthday_next', 'x_anniversary_next',
                     'x_next_occasion_date', 'x_next_occasion_type',
                     'x_days_to_occasion'):
            self.env.add_to_compute(self._fields[name], self)
        self.flush_recordset()
        return True

    # ------------------------------------------------------------------
    # Reading them
    # ------------------------------------------------------------------

    @api.model
    def _samra_occasion_domain(self, days=HORIZON_DAYS):
        today = fields.Date.context_today(self)
        return self._samra_customer_domain([
            ('x_next_occasion_date', '!=', False),
            ('x_next_occasion_date', '<=', fields.Date.to_string(
                today + timedelta(days=days))),
        ])

    @api.model
    def samra_upcoming_occasions(self, days=HORIZON_DAYS, limit=20):
        """The occasion list the dashboard paints.

        Ordered by how soon, not by how valuable: the point of the panel is
        that there is a window, and a VVIP whose birthday was yesterday is no
        longer actionable. Tier rides along so the list can still be triaged.
        """
        domain = self._samra_occasion_domain(days)
        partners = self.search(domain, order='x_next_occasion_date asc', limit=limit)
        return {
            'days': days,
            'count': self.search_count(domain),
            'domain': domain,
            'occasions': [{
                'id': partner.id,
                'name': partner.display_name,
                'type': partner.x_next_occasion_type,
                'label': self.env._(
                    OCCASION_LABELS.get(partner.x_next_occasion_type, '')),
                'date': fields.Date.to_string(partner.x_next_occasion_date),
                'days_away': partner.x_days_to_occasion,
                'vip_tier': partner.x_vip_tier or 'regular',
                'lifetime_value': partner.x_lifetime_value or 0.0,
                'phone': partner.phone or '',
                'salesperson': partner.user_id.display_name or '',
                'last_purchase': fields.Date.to_string(partner.x_last_purchase_date)
                                 if partner.x_last_purchase_date else None,
                'wishlist_count': partner.x_wishlist_count,
                'wishlist_value': partner.x_wishlist_value,
                'whatsapp_consent': bool(partner.x_whatsapp_consent),
            } for partner in partners],
        }
