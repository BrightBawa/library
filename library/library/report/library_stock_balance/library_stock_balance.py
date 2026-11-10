# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	warehouse = frappe.db.get_single_value("Library Settings", "library_warehouse")
	conds, values = "", {"warehouse": warehouse}
	for field in ("book_type", "category"):
		if filters.get(field):
			conds += f" and lb.{field} = %({field})s"
			values[field] = filters.get(field)
	data = frappe.db.sql(f"""
		select lb.name book, lb.book_title, lb.book_type, lb.category, lb.item,
			ifnull(b.actual_qty, 0) warehouse_qty, ifnull(b.valuation_rate, 0) valuation_rate, ifnull(b.stock_value, 0) stock_value,
			(select count(*) from `tabLibrary Book Copy` c where c.book = lb.name and c.status != 'Lost') copies,
			(select count(*) from `tabLibrary Book Copy` c where c.book = lb.name and c.status = 'Available') available,
			(select count(*) from `tabLibrary Book Copy` c where c.book = lb.name and c.status = 'Issued') on_loan,
			(select count(*) from `tabLibrary Book Copy` c where c.book = lb.name and c.status in ('Lost', 'Damaged')) lost_or_damaged
		from `tabLibrary Book` lb
		left join tabBin b on b.item_code = lb.item and b.warehouse = %(warehouse)s and lb.book_type = 'Issue'
		where 1 = 1 {conds} order by lb.book_type, lb.book_title
	""", values, as_dict=True)
	return columns(), data


def columns():
	return [
		{"fieldname": "book", "label": _("Book"), "fieldtype": "Link", "options": "Library Book", "width": 110},
		{"fieldname": "book_title", "label": _("Title"), "fieldtype": "Data", "width": 200},
		{"fieldname": "book_type", "label": _("Type"), "fieldtype": "Data", "width": 75},
		{"fieldname": "category", "label": _("Category"), "fieldtype": "Link", "options": "Library Category", "width": 120},
		{"fieldname": "item", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "warehouse_qty", "label": _("In Library Warehouse"), "fieldtype": "Float", "width": 120},
		{"fieldname": "valuation_rate", "label": _("Valuation Rate"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "stock_value", "label": _("Stock Value"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "copies", "label": _("Copies"), "fieldtype": "Int", "width": 70},
		{"fieldname": "available", "label": _("Available"), "fieldtype": "Int", "width": 80},
		{"fieldname": "on_loan", "label": _("On Loan"), "fieldtype": "Int", "width": 75},
		{"fieldname": "lost_or_damaged", "label": _("Lost / Damaged"), "fieldtype": "Int", "width": 105},
	]
