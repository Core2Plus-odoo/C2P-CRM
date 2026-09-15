# -*- coding: utf-8 -*-
"""Live breakdowns for the Customer 360 profile.

Everything here is computed from the customer's actual order lines at the
moment the profile opens, not read from the stored fields the nightly cron
maintains. Those stored fields still exist and still drive list views,
searching and the dashboard's aggregate queries -- they have to, because you
cannot sort 40,000 partners by a figure computed in Python. But on a single
profile the customer is right there in front of the associate, so the numbers
should be true now rather than true as of 2am.

One customer's order history is small enough to bucket in Python. Doing it
that way rather than through grouped reads keeps every breakdown consistent
with the same line set, and avoids six round trips to produce six panels.
"""

from collections import defaultdict
from datetime import date

from odoo import api, fields, models

from .samra_metrics import CONFIRMED_STATES

MONTHS_OF_HISTORY = 6
TOP_N = 5

MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

def _month_key(value):
    return (value.year, value.month)

def _month_label(year, month):
    return f"{MONTH_LABELS[month - 1]} {str(year)[2:]}"

def _shift_month(year, month, delta):
    index = (year * 12 + (month - 1)) + delta
    return index // 12, index % 12 + 1

class ResPartnerAnalytics(models.Model):
    _inherit = 'res.partner'

    # ------------------------------------------------------------------
    # Source data
    # ------------------------------------------------------------------

    def _samra_confirmed_orders(self):
        self.ensure_one()
        return self.env['sale.order'].search(
            [('partner_id', '=', self.id), ('state', 'in', list(CONFIRMED_STATES))],
            order='date_order asc',
        )

    # ------------------------------------------------------------------
    # Breakdowns
    # ------------------------------------------------------------------

    @api.model
    def _samra_rank(self, totals, limit=TOP_N):
        """Turn {label: {...}} into a sorted list carrying each row's share.

        Share is of the ranked total, so the bars in a panel always fill their
        track -- a bar chart whose longest bar stops at 40% reads as broken.
        """
        rows = sorted(totals.values(), key=lambda row: row['revenue'], reverse=True)
        rows = rows[:limit]
        peak = max((row['revenue'] for row in rows), default=0.0)
        for row in rows:
            row['share'] = (row['revenue'] / peak * 100) if peak else 0.0
        return rows

    def _samra_monthly(self, orders, months=MONTHS_OF_HISTORY):
        """A dense month series -- months with no purchase are zeros, not gaps.

        A sparse series would silently compress a quiet summer into nothing and
        make the trend look steadier than it was.
        """
        self.ensure_one()
        today = date.today()
        buckets = {}
        for offset in range(months - 1, -1, -1):
            year, month = _shift_month(today.year, today.month, -offset)
            buckets[(year, month)] = {
                'label': _month_label(year, month),
                'revenue': 0.0,
                'orders': 0,
            }

        for order in orders:
            if not order.date_order:
                continue
            key = _month_key(order.date_order)
            if key in buckets:
                buckets[key]['revenue'] += order.amount_total
                buckets[key]['orders'] += 1

        series = list(buckets.values())
        peak = max((row['revenue'] for row in series), default=0.0)
        for row in series:
            row['share'] = (row['revenue'] / peak * 100) if peak else 0.0
        return series

    def _samra_dimension(self, orders, key_fn, label_fn):
        """Aggregate order lines by whatever key_fn pulls off the product."""
        totals = defaultdict(lambda: {'label': '', 'revenue': 0.0, 'qty': 0.0})
        for order in orders:
            for line in order.order_line:
                if not line.product_id or line.display_type:
                    continue
                key = key_fn(line)
                if not key:
                    continue
                bucket = totals[key]
                bucket['label'] = label_fn(line)
                bucket['revenue'] += line.price_subtotal
                bucket['qty'] += line.product_uom_qty
        return self._samra_rank(totals)

    def _samra_cadence(self, orders):
        """Average days between purchases, and whether the gap is widening.

        Two purchases give one interval, which is a fact but not a trend, so
        the comparison only appears once there are enough of them to mean
        something.
        """
        dates = [o.date_order.date() for o in orders if o.date_order]
        if len(dates) < 2:
            return {'average_days': None, 'recent_days': None, 'slowing': False}

        gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
        average = sum(gaps) / len(gaps)

        recent = None
        slowing = False
        if len(gaps) >= 4:
            half = len(gaps) // 2
            recent = sum(gaps[half:]) / len(gaps[half:])
            slowing = recent > average * 1.25

        return {
            'average_days': round(average),
            'recent_days': round(recent) if recent is not None else None,
            'slowing': slowing,
        }

    def _samra_tier_progress(self, lifetime_value):
        """How far this customer is from the next tier."""
        self.ensure_one()
        vip, vvip = self._samra_tier_thresholds()
        tier = self.x_vip_tier or 'regular'

        if tier == 'vvip' or lifetime_value >= vvip:
            return {'next_tier': None, 'remaining': 0.0, 'progress': 100.0,
                    'threshold': vvip}

        target = vip if lifetime_value < vip else vvip
        label = 'VIP' if target == vip else 'VVIP'
        floor = 0.0 if target == vip else vip
        span = target - floor
        progress = ((lifetime_value - floor) / span * 100) if span else 0.0

        return {
            'next_tier': label,
            'remaining': max(target - lifetime_value, 0.0),
            'progress': max(min(progress, 100.0), 0.0),
            'threshold': target,
        }

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def _samra_analytics(self):
        self.ensure_one()
        orders = self._samra_confirmed_orders()

        revenue = sum(orders.mapped('amount_total'))
        count = len(orders)
        dates = [o.date_order for o in orders if o.date_order]

        lines = [line for order in orders for line in order.order_line
                 if line.product_id and not line.display_type]
        gold_weight = sum(
            (line.product_id.x_gold_weight or 0.0) * line.product_uom_qty for line in lines)

        largest = max(orders, key=lambda o: o.amount_total, default=None)

        wishlist = self.env['x_samra_wishlist'].search([('x_partner_id', '=', self.id)])
        messages = self.env['x_samra_whatsapp_log'].search([('x_partner_id', '=', self.id)])
        viewed = self.env['x_samra_viewed_product'].search_count([('x_partner_id', '=', self.id)])

        return {
            'months': MONTHS_OF_HISTORY,
            'lifetime_value': revenue,
            'order_count': count,
            'average_order_value': (revenue / count) if count else 0.0,
            'largest_order': {
                'name': largest.name if largest else '',
                'id': largest.id if largest else False,
                'amount': largest.amount_total if largest else 0.0,
            },
            'first_purchase': fields.Date.to_string(min(dates).date()) if dates else None,
            'last_purchase': fields.Date.to_string(max(dates).date()) if dates else None,
            'pieces': sum(line.product_uom_qty for line in lines),
            'gold_weight': gold_weight,
            'monthly': self._samra_monthly(orders),
            'by_branch': self._samra_dimension(
                orders,
                lambda line: line.order_id.warehouse_id.id,
                lambda line: line.order_id.warehouse_id.display_name or 'Unassigned'),
            'by_category': self._samra_dimension(
                orders,
                lambda line: line.product_id.categ_id.id,
                lambda line: line.product_id.categ_id.display_name or 'Uncategorised'),
            'by_collection': self._samra_dimension(
                orders,
                lambda line: line.product_id.x_collection,
                lambda line: line.product_id.x_collection or ''),
            'by_salesperson': self._samra_dimension(
                orders,
                lambda line: line.order_id.user_id.id,
                lambda line: line.order_id.user_id.display_name or 'Unassigned'),
            'top_products': self._samra_dimension(
                orders,
                lambda line: line.product_id.id,
                lambda line: line.product_id.display_name),
            'cadence': self._samra_cadence(orders),
            'tier_progress': self._samra_tier_progress(revenue),
            'engagement': {
                'wishlist_items': len(wishlist),
                'wishlist_value': sum(wishlist.mapped('x_price')),
                'viewed_products': viewed,
                'messages': len(messages),
                'messages_in': len(messages.filtered(lambda m: m.x_direction == 'inbound')),
                'messages_out': len(messages.filtered(lambda m: m.x_direction != 'inbound')),
            },
        }
