# -*- coding: utf-8 -*-
"""Scheduled recomputation of customer purchase metrics.

Requirement 8 asks the system to calculate lifetime spend and purchase
frequency automatically. The fields existed and were read all over the
product -- the profile headline, VIP tiering, the reactivation list, the
dashboard's inactive count -- but nothing wrote them, so every one of those
figures was only as fresh as whatever last touched the database by hand.

These are stored fields refreshed on a schedule rather than computed fields
with a depends on the order history: a jeweller's partner record would
otherwise be invalidated by every confirmation, every invoice and every POS
line, and the recompute cost lands on the till.
"""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Orders that represent money actually committed.
CONFIRMED_STATES = ('sale', 'done')

# Default tier thresholds in company currency. Overridable without a code
# change through Settings -> Technical -> System Parameters.
PARAM_VIP_THRESHOLD = 'samra_crm.vip_threshold'
PARAM_VVIP_THRESHOLD = 'samra_crm.vvip_threshold'
DEFAULT_VIP_THRESHOLD = 100000.0
DEFAULT_VVIP_THRESHOLD = 300000.0

# How many partners to write per flush, so a large run doesn't hold one
# enormous transaction open.
BATCH_SIZE = 500


class ResPartnerMetrics(models.Model):
    _inherit = 'res.partner'

    x_vip_tier_manual = fields.Boolean(
        string='VIP Tier Set Manually',
        help='When set, the scheduled recomputation will not change this '
             'customer\'s tier. Requirement 7 allows a tier to be assigned by '
             'hand as well as earned by spend; without this flag the next run '
             'would quietly undo the manual decision.',
    )

    # ------------------------------------------------------------------
    # Thresholds
    # ------------------------------------------------------------------

    @api.model
    def _samra_tier_thresholds(self):
        params = self.env['ir.config_parameter'].sudo()

        def _read(key, default):
            try:
                return float(params.get_param(key, default))
            except (TypeError, ValueError):
                _logger.warning(
                    "Samra CRM: %s is not a number; falling back to %s", key, default)
                return default

        return (
            _read(PARAM_VIP_THRESHOLD, DEFAULT_VIP_THRESHOLD),
            _read(PARAM_VVIP_THRESHOLD, DEFAULT_VVIP_THRESHOLD),
        )

    @api.model
    def _samra_tier_for_value(self, lifetime_value, vip, vvip):
        if lifetime_value >= vvip:
            return 'vvip'
        if lifetime_value >= vip:
            return 'vip'
        return 'regular'

    # ------------------------------------------------------------------
    # Recomputation
    # ------------------------------------------------------------------

    @api.model
    def _samra_purchase_metrics(self, partners):
        """Aggregate confirmed orders per partner in one grouped read."""
        groups = self.env['sale.order']._read_group(
            [('partner_id', 'in', partners.ids),
             ('state', 'in', list(CONFIRMED_STATES))],
            ['partner_id'],
            ['amount_total:sum', '__count', 'date_order:max'],
        )
        return {
            partner.id: {
                'total': total or 0.0,
                'count': count,
                'last': last,
            }
            for partner, total, count, last in groups
        }

    def _samra_apply_metrics(self, metrics, vip, vvip):
        """Write metrics onto partners, touching only what actually changed."""
        updated = 0
        for partner in self:
            data = metrics.get(partner.id)
            total = data['total'] if data else 0.0
            count = data['count'] if data else 0
            last = data['last'].date() if data and data['last'] else False

            values = {}
            # Float comparison at fils precision: a sub-centime difference is
            # rounding noise, not a change worth a write and a tracking entry.
            if abs((partner.x_lifetime_value or 0.0) - total) > 0.005:
                values['x_lifetime_value'] = total
            if (partner.x_purchase_frequency or 0) != count:
                values['x_purchase_frequency'] = count
            if (partner.x_last_purchase_date or False) != last:
                values['x_last_purchase_date'] = last

            if not partner.x_vip_tier_manual:
                tier = self._samra_tier_for_value(total, vip, vvip)
                if (partner.x_vip_tier or 'regular') != tier:
                    values['x_vip_tier'] = tier

            if values:
                partner.write(values)
                updated += 1
        return updated

    @api.model
    def _cron_recompute_customer_metrics(self):
        """Entry point for the scheduled action.

        Covers every customer, including those with no orders at all -- their
        metrics must be zeroed, otherwise a customer whose only order was
        cancelled keeps a lifetime value forever and never appears in the
        reactivation list.
        """
        vip, vvip = self._samra_tier_thresholds()
        partners = self.search([('customer_rank', '>', 0)])
        _logger.info("Samra CRM: recomputing metrics for %s customers", len(partners))

        updated = 0
        for index in range(0, len(partners), BATCH_SIZE):
            batch = partners[index:index + BATCH_SIZE]
            metrics = self._samra_purchase_metrics(batch)
            updated += batch._samra_apply_metrics(metrics, vip, vvip)
            self.env.cr.commit()

        _logger.info("Samra CRM: %s customer(s) updated", updated)
        return updated

    def action_samra_recompute_metrics(self):
        """Recompute on demand, for the selected customers."""
        vip, vvip = self._samra_tier_thresholds()
        metrics = self._samra_purchase_metrics(self)
        self._samra_apply_metrics(metrics, vip, vvip)
        return True
