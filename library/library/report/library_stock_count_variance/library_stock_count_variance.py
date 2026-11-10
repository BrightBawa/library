# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

from library.library.reporting import date_conditions


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conds, values = date_conditions(filters, "c.posting_date")
	if filters.stock_count:
		conds += " and c.name = %(stock_count)s"
		values["stock_count"] = filters.stock_count
	data = frappe.db.sql(f"""
		select c.posting_date, c.name stock_count, i.book_title, %(books)s kind, i.system_qty, i.counted_qty, i.variance,
			i.valuation_rate, i.variance * i.valuation_rate variance_value
		from `tabLibrary Stock Count` c join `tabLibrary Stock Count Item` i on i.parent = c.name
		where c.docstatus = 1 and i.variance != 0 {conds}
		union all
		select c.posting_date, c.name, p.book_title, %(copy)s, 1, 0, -1, 0, 0
		from `tabLibrary Stock Count` c join `tabLibrary Stock Count Copy` p on p.parent = c.name
		where c.docstatus = 1 and p.found = 0 {conds}
		order by 1, 2, 3""", dict(values, books=_("Issue-type stock"), copy=_("Copy not found")), as_dict=True)
	return columns(), data


def columns():
	return [
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "stock_count", "label": _("Stock Count"), "fieldtype": "Link", "options": "Library Stock Count", "width": 140},
		{"fieldname": "book_title", "label": _("Book"), "fieldtype": "Data", "width": 200},
		{"fieldname": "kind", "label": _("Kind"), "fieldtype": "Data", "width": 120},
		{"fieldname": "system_qty", "label": _("System"), "fieldtype": "Float", "width": 80},
		{"fieldname": "counted_qty", "label": _("Counted"), "fieldtype": "Float", "width": 80},
		{"fieldname": "variance", "label": _("Variance"), "fieldtype": "Float", "width": 80},
		{"fieldname": "valuation_rate", "label": _("Valuation Rate"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "variance_value", "label": _("Variance Value"), "fieldtype": "Currency", "width": 120},
	]
