# -*- coding: utf-8 -*-
"""REST integration surface for external systems.

Odoo already exposes XML-RPC, but that requires the caller to know Odoo's
model and field names. These endpoints present a stable, documented contract
instead, so a POS, accounting package or storefront can integrate without
tracking internal schema changes.

Auth reuses Odoo's own API key store (Settings -> Users -> Account Security ->
API Keys) rather than inventing a parallel credential scheme: keys can be
issued and revoked per integration user through standard Odoo UI, and the
permissions that apply are that user's ordinary access rights.

    X-API-Key: <the user's Odoo API key>

Responses are plain JSON with conventional status codes -- not Odoo's JSON-RPC
envelope, which would force integrators to unwrap a 200 to discover an error.
"""

import functools
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

API_ROOT = '/api/samra'

# Odoo's own scope for programmatic keys; a key created for XML-RPC works here.
API_KEY_SCOPE = 'rpc'


def _json(payload, status=200):
    return request.make_json_response(payload, status=status)


def _error(message, status, code=None):
    return _json({'error': {'code': code or status, 'message': message}}, status=status)


def api_endpoint(func):
    """Authenticate by API key, then run as that user.

    Every endpoint below is declared auth='none' so this wrapper owns the
    401 -- Odoo's own auth would redirect a browser to a login page, which is
    useless to a machine caller.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        key = request.httprequest.headers.get('X-API-Key')
        if not key:
            return _error('Missing X-API-Key header.', 401)

        uid = request.env['res.users.apikeys'].sudo()._check_credentials(
            scope=API_KEY_SCOPE, key=key)
        if not uid:
            return _error('Invalid or revoked API key.', 401)

        request.update_env(user=uid)

        try:
            return func(*args, **kwargs)
        except ValueError as exc:
            return _error(str(exc), 400)
        except Exception:
            # Never leak a traceback to an integrator; log it for us instead.
            _logger.exception("Samra API error in %s", func.__name__)
            return _error('Internal error. The incident has been logged.', 500)

    return wrapper


def _read_json_body():
    raw = request.httprequest.get_data()
    if not raw:
        raise ValueError('Request body is empty; expected JSON.')
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        raise ValueError('Request body is not valid JSON.')
    if not isinstance(payload, dict):
        raise ValueError('Request body must be a JSON object.')
    return payload


class SamraAPI(http.Controller):

    # ------------------------------------------------------------------
    # GET /api/samra/customers/<id>
    # ------------------------------------------------------------------
    @http.route(f'{API_ROOT}/customers/<int:partner_id>', type='http',
                auth='none', methods=['GET'], csrf=False)
    @api_endpoint
    def get_customer(self, partner_id, **kwargs):
        partner = request.env['res.partner'].browse(partner_id).exists()
        if not partner:
            return _error(f'No customer with id {partner_id}.', 404)

        profile = partner.get_samra_profile()
        return _json({
            'id': profile['id'],
            'name': profile['name'],
            'email': profile['email'],
            'phone': profile['phone'],
            'city': profile['city'],
            'nationality': profile['nationality'],
            'vip_tier': profile['vip_tier'],
            'salesperson': profile['salesperson'],
            'tags': [tag['name'] for tag in profile['tags']],
            'consent': profile['consent'],
            'preferences': profile['preferences'],
            'purchase_summary': {
                'lifetime_value': profile['stats']['lifetime_value'],
                'purchase_frequency': profile['stats']['purchase_frequency'],
                'last_purchase_date': profile['stats']['last_purchase_date'],
                'days_since_purchase': profile['stats']['days_since_purchase'],
                'at_risk': profile['stats']['at_risk'],
            },
            'recent_orders': profile['orders'],
            'currency': profile['currency'],
        })

    # ------------------------------------------------------------------
    # GET /api/samra/stock/<product_id>
    # ------------------------------------------------------------------
    @http.route(f'{API_ROOT}/stock/<int:product_id>', type='http',
                auth='none', methods=['GET'], csrf=False)
    @api_endpoint
    def get_stock(self, product_id, **kwargs):
        product = request.env['product.product'].browse(product_id).exists()
        if not product:
            return _error(f'No product with id {product_id}.', 404)

        branches = []
        total = 0.0
        for warehouse in request.env['stock.warehouse'].search([]):
            location = warehouse.lot_stock_id
            if not location:
                continue
            groups = request.env['stock.quant']._read_group(
                [('product_id', '=', product.id), ('location_id', 'child_of', location.id)],
                [], ['quantity:sum', 'reserved_quantity:sum'],
            )
            on_hand, reserved = (groups[0] if groups else (0.0, 0.0))
            on_hand = on_hand or 0.0
            reserved = reserved or 0.0
            total += on_hand
            branches.append({
                'warehouse_id': warehouse.id,
                'branch': warehouse.display_name,
                'quantity_on_hand': on_hand,
                'quantity_reserved': reserved,
                'quantity_available': on_hand - reserved,
            })

        return _json({
            'product_id': product.id,
            'sku': product.default_code or '',
            'name': product.display_name,
            'list_price': product.list_price,
            'gold_weight': product.x_gold_weight,
            'stone_details': product.x_stone_details or '',
            'total_on_hand': total,
            'branches': branches,
        })

    # ------------------------------------------------------------------
    # POST /api/samra/orders
    # ------------------------------------------------------------------
    @http.route(f'{API_ROOT}/orders', type='http',
                auth='none', methods=['POST'], csrf=False)
    @api_endpoint
    def create_order(self, **kwargs):
        payload = _read_json_body()

        partner_id = payload.get('partner_id')
        if not partner_id:
            raise ValueError('partner_id is required.')

        partner = request.env['res.partner'].browse(int(partner_id)).exists()
        if not partner:
            return _error(f'No customer with id {partner_id}.', 404)

        lines = payload.get('lines') or []
        if not isinstance(lines, list) or not lines:
            raise ValueError('lines must be a non-empty array of {product_id, quantity}.')

        order_lines = []
        for index, line in enumerate(lines):
            if not isinstance(line, dict) or not line.get('product_id'):
                raise ValueError(f'lines[{index}] must be an object with a product_id.')

            product = request.env['product.product'].browse(
                int(line['product_id'])).exists()
            if not product:
                return _error(
                    f"lines[{index}]: no product with id {line['product_id']}.", 404)

            values = {
                'product_id': product.id,
                'product_uom_qty': float(line.get('quantity') or 1),
            }
            # Honour an externally-priced line (a POS discount, say) but let
            # Odoo price it otherwise.
            if line.get('price_unit') is not None:
                values['price_unit'] = float(line['price_unit'])
            order_lines.append((0, 0, values))

        order_values = {'partner_id': partner.id, 'order_line': order_lines}

        if payload.get('warehouse_id'):
            warehouse = request.env['stock.warehouse'].browse(
                int(payload['warehouse_id'])).exists()
            if not warehouse:
                return _error(f"No warehouse with id {payload['warehouse_id']}.", 404)
            order_values['warehouse_id'] = warehouse.id

        if payload.get('client_order_ref'):
            order_values['client_order_ref'] = str(payload['client_order_ref'])

        order = request.env['sale.order'].create(order_values)

        if payload.get('confirm'):
            order.action_confirm()

        return _json({
            'id': order.id,
            'name': order.name,
            'state': order.state,
            'partner_id': order.partner_id.id,
            'amount_untaxed': order.amount_untaxed,
            'amount_tax': order.amount_tax,
            'amount_total': order.amount_total,
            'currency': order.currency_id.name,
        }, status=201)

    # ------------------------------------------------------------------
    # GET /api/samra/loyalty/<partner_id>
    # ------------------------------------------------------------------
    @http.route(f'{API_ROOT}/loyalty/<int:partner_id>', type='http',
                auth='none', methods=['GET'], csrf=False)
    @api_endpoint
    def get_loyalty(self, partner_id, **kwargs):
        partner = request.env['res.partner'].browse(partner_id).exists()
        if not partner:
            return _error(f'No customer with id {partner_id}.', 404)

        loyalty = partner._samra_loyalty()
        return _json({
            'partner_id': partner.id,
            'name': partner.display_name,
            'vip_tier': partner.x_vip_tier or 'regular',
            'points_balance': loyalty['points'],
            'rewards': loyalty['rewards'],
        })
