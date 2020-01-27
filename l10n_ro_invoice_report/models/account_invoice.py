# Copyright 2015 Deltatech
# Copyright 2018 OdooERP Romania
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from functools import partial
from odoo.tools.misc import formatLang

from odoo import api, fields, models


class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    @api.one
    @api.depends('invoice_line_ids.price_subtotal', 'tax_line_ids.amount',
                 'tax_line_ids.amount_rounding', 'currency_id', 'company_id',
                 'date_invoice', 'type')
    def _compute_amount(self):
        super(AccountInvoice, self)._compute_amount()
        if self.currency_id and self.company_id and \
                self.currency_id != self.company_id.currency_id:
            currency_id = self.currency_id.with_context(
                date=self.date_invoice)
            self.amount_tax_company_signed = currency_id.compute(
                self.amount_tax, self.company_id.currency_id)

    @api.one
    @api.depends('currency_id', 'date_invoice')
    def _compute_currency_rate(self):
        if self.currency_id:
            currency_id = self.currency_id.with_context(
                date=self.date_invoice)
            company_currency_id = self.company_currency_id.with_context(
                date=self.date_invoice)
            self.currency_rate = self.env['res.currency']._get_conversion_rate(
                currency_id, company_currency_id)

    @api.multi
    def _get_tax_amount_by_group(self):
        self.ensure_one()
        result = super(AccountInvoice, self)._get_tax_amount_by_group()
        currency = self.currency_id.with_context(date=self.date_invoice)
        fmt = partial(formatLang,
                      self.with_context(lang=self.partner_id.lang).env,
                      currency_obj=self.company_id.currency_id)
        for line in result:
            if self.currency_id != self.company_id.currency_id:
                new_line = line
                comp_amount = currency.compute(line[1],
                                               self.company_id.currency_id)
                comp_base = currency.compute(line[2],
                                             self.company_id.currency_id)
                new_line += (comp_amount, comp_base,
                             fmt(comp_amount), fmt(comp_base))
                result.remove(line)
                result.append(new_line)
        return result

    currency_rate = fields.Float(
        string='Currency Rate', store=True, readonly=True,
        compute='_compute_currency_rate')
    amount_tax_company_signed = fields.Monetary(
        string='Tax in Company Currency', currency_field='company_currency_id',
        store=True, readonly=True, compute='_compute_amount',
        help="Tax amount in the currency of the company, "
             "negative for credit notes.")


class AccountInvoiceLine(models.Model):
    _inherit = "account.invoice.line"

    @api.one
    @api.depends('price_unit', 'discount', 'invoice_line_tax_ids', 'quantity',
                 'product_id', 'invoice_id.partner_id',
                 'invoice_id.currency_id', 'invoice_id.company_id',
                 'invoice_id.date_invoice', 'invoice_id.date')
    def _compute_price(self):
        super(AccountInvoiceLine, self)._compute_price()
        currency = self.invoice_id and self.invoice_id.currency_id or None
        price = self.price_unit * (1 - (self.discount or 0.0) / 100.0)
        taxes = taxes_unit = normal_taxes = False
        self.price_taxes = self.price_total - self.price_subtotal
        self.price_unit_without_taxes = self.price_subtotal / self.quantity

        # Compute normal taxes in case of Customer Invoices to have the value
        # in Inverse Taxation
        if self.invoice_id.type in ['out_invoice', 'out_refund']:
            normal_taxes = self.product_id.taxes_id.compute_all(
                price, currency, self.quantity, product=self.product_id,
                partner=self.invoice_id.partner_id)
        else:
            normal_taxes = self.product_id.supplier_taxes_id.compute_all(
                price, currency, self.quantity, product=self.product_id,
                partner=self.invoice_id.partner_id)
        if normal_taxes:
            self.price_normal_taxes = \
                normal_taxes['total_included'] - normal_taxes['total_excluded']

    price_unit_without_taxes = fields.Float(
        string='Price Unit without taxes',
        store=True, readonly=True, compute='_compute_price',
        help="Price Unit without tax (if tax included)")
    price_taxes = fields.Float(
        string='Taxes', store=True, readonly=True, compute='_compute_price',
        help="Total amount of taxes")
    price_normal_taxes = fields.Float(
        string='Normal Taxes', store=True, readonly=True,
        compute='_compute_price',
        help="Total amount of taxes, from product taxes")
