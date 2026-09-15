# -*- coding: utf-8 -*-
"""The morning rate, and the arithmetic that hangs off it.

Every jewellery price in the shop is derived from one number that changes
daily. Getting that number into Odoo, and out again as a sales price, is the
whole job of this file.

WHY RATES ARE COMPANY-SHARED
Samra runs four companies. A gold rate is a fact about the Dubai market, not
about a branch: all four read the same figure on the same morning, and
entering it four times would guarantee they eventually disagree. So rate
records carry no company_id, which in Odoo means every company sees them.
Making-charge policy is the opposite -- a commercial decision each company
makes for itself -- so that lives on the product, which can be company-scoped.

WHY KARATS ARE A FIXED SET
24, 22, 21, 18 and 14 are the karats a UAE retailer actually trades; 21 is the
Gulf staple that surprises people used to Indian or European markets. A
configurable purity model would be more general and would earn nothing: the
set has not changed in a century, and every extra table is another thing to
get the ACLs wrong on.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Millesimal fineness: the fraction of the alloy that is actually gold.
# 21K is 0.875 and dominates Gulf retail; 22K (0.916) is the Indian standard.
PURITY = {
    '24': 0.999,
    '22': 0.916,
    '21': 0.875,
    '18': 0.750,
    '14': 0.585,
}

KARAT_SELECTION = [
    ('24', '24K'),
    ('22', '22K'),
    ('21', '21K'),
    ('18', '18K'),
    ('14', '14K'),
]


class SamraGoldRate(models.Model):
    _name = 'samra.gold.rate'
    _description = 'Samra Daily Gold Rate'
    _order = 'rate_date desc, karat desc'
    _rec_name = 'display_name'

    rate_date = fields.Date(
        string='Date', required=True, index=True,
        default=fields.Date.context_today,
        help='The trading day this rate applies to.')
    karat = fields.Selection(
        KARAT_SELECTION, string='Karat', required=True, default='22', index=True)
    rate_per_gram = fields.Float(
        string='Rate per Gram', required=True, digits='Product Price',
        help='Price of one gram of this karat, in company currency.')
    source = fields.Char(
        string='Source',
        help='Where the figure came from, e.g. Dubai Gold & Jewellery Group. '
             'Recorded so a disputed price can be traced back to its quote.')
    note = fields.Char(string='Note')

    applied_on = fields.Datetime(
        string='Applied On', readonly=True,
        help='When this rate was last pushed onto product sales prices.')
    applied_count = fields.Integer(
        string='Products Priced', readonly=True)

    # One rate per karat per day. Two figures for the same morning is not a
    # correction, it is an argument nobody can settle afterwards -- edit the
    # existing row instead so the change is tracked.
    #
    # models.Constraint, not _sql_constraints: the list form was dropped in
    # Odoo 19 and now only logs a warning, which means the constraint silently
    # is not there. The local install caught it.
    _date_karat_uniq = models.Constraint(
        'unique(rate_date, karat)',
        'A rate for that karat already exists on that date. Edit it rather '
        'than adding a second one.')

    @api.depends('rate_date', 'karat', 'rate_per_gram')
    def _compute_display_name(self):
        labels = dict(KARAT_SELECTION)
        for record in self:
            date = fields.Date.to_string(record.rate_date) or ''
            record.display_name = f"{labels.get(record.karat, record.karat)} · {date}"

    @api.constrains('rate_per_gram')
    def _check_rate_positive(self):
        for record in self:
            if record.rate_per_gram <= 0:
                raise ValidationError(_("A gold rate must be greater than zero."))

    # ------------------------------------------------------------------
    # Reading the rate
    # ------------------------------------------------------------------

    @api.model
    def _rate_for(self, karat, on_date=None):
        """The rate per gram for a karat, on or before a date.

        Falls back to deriving from any other karat quoted that day, scaled by
        fineness, because a shop that only posts its 22K figure still has a
        defensible 18K price. Falls back again to the most recent earlier
        quote, because a public holiday should not make the tills unable to
        price anything.

        Returns 0.0 when nothing has ever been entered. Callers treat that as
        "no metal component" rather than raising, so an ordinary non-gold
        product is not an error.
        """
        on_date = on_date or fields.Date.context_today(self)

        exact = self.sudo().search([
            ('karat', '=', karat),
            ('rate_date', '<=', on_date),
        ], order='rate_date desc', limit=1)
        if exact:
            return exact.rate_per_gram

        # Nothing for this karat: derive from whatever else was quoted.
        other = self.sudo().search(
            [('rate_date', '<=', on_date)], order='rate_date desc', limit=1)
        if not other:
            return 0.0

        source_fineness = PURITY.get(other.karat)
        target_fineness = PURITY.get(karat)
        if not source_fineness or not target_fineness:
            return 0.0
        return other.rate_per_gram / source_fineness * target_fineness

    @api.model
    def _latest_date(self):
        latest = self.sudo().search([], order='rate_date desc', limit=1)
        return latest.rate_date or False

    # ------------------------------------------------------------------
    # Pushing it onto prices
    # ------------------------------------------------------------------

    def action_apply_to_products(self):
        """Recompute sales prices for every gold product of this karat.

        Writing into list_price rather than intercepting price at each point
        of sale is the central decision of this module. Once the ordinary
        sales price is right for today, quotations, the POS, pricelists,
        promotions and margin reporting all work unchanged. Intercepting
        instead would mean shipping the rate table into the POS, which runs
        its own trimmed frontend and is meant to keep selling offline.
        """
        self.ensure_one()
        touched, total = self._apply_to_products()
        if total is None:
            raise UserError(_(
                "No gold products are set to %s. Tick 'Gold Item' on a product "
                "and give it a karat first.", dict(KARAT_SELECTION)[self.karat]))
        return self._notify(_(
            "%(touched)s of %(total)s %(karat)s product(s) repriced.",
            touched=touched, total=total,
            karat=dict(KARAT_SELECTION)[self.karat]))

    def _apply_to_products(self):
        """Do the repricing. Returns (repriced, considered).

        Split from the button so that "no products at this karat" is a return
        value here and an error message there. It is worth telling someone who
        clicked Apply that nothing happened; it is not worth making the nightly
        run catch an exception to discover the same thing, and exception-as-
        control-flow across a transaction boundary is how cursors get left in
        a state nobody can debug.

        (repriced, None) means there was nothing to consider at all.
        """
        self.ensure_one()

        products = self.env['product.template'].search([
            ('x_is_gold', '=', True),
            ('x_karat', '=', self.karat),
        ])
        if not products:
            return 0, None

        touched = 0
        for product in products:
            price = product._samra_gold_price(rate=self.rate_per_gram)
            # Rounding noise is not a price change, and a write here would
            # bloat the tracking history on every product every morning.
            if abs((product.list_price or 0.0) - price) > 0.005:
                product.list_price = price
                touched += 1

        self.write({
            'applied_on': fields.Datetime.now(),
            'applied_count': touched,
        })
        return touched, len(products)

    @api.model
    def action_apply_latest(self):
        """Apply the most recent rate for every karat. Safe to run from cron.

        Idempotent: applying a rate that is already reflected in prices writes
        nothing, so a cron that fires twice costs two reads and no history.
        """
        applied = []
        for karat, _label in KARAT_SELECTION:
            rate = self.sudo().search(
                [('karat', '=', karat)], order='rate_date desc', limit=1)
            if not rate:
                continue
            _touched, total = rate._apply_to_products()
            if total:
                applied.append(karat)
        return applied

    def _notify(self, message):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Gold rate applied"),
                'message': message,
                'type': 'success',
                'sticky': False,
            },
        }
