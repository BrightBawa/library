# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from library.library.reporting import date_conditions


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conds, values = date_conditions(filters, "i.posting_date", "i.academic_year")
	for field in ("student", "student_batch"):
		if filters.get(field):
			conds += f" and i.{field} = %({field})s"
			values[field] = filters.get(field)
	if filters.billing in ("Billed", "Free"):
		conds += " and r.is_billable = %(billable)s"
		values["billable"] = 1 if filters.billing == "Billed" else 0
	data = frappe.db.sql(f"""
		select i.posting_date, i.name issuance, i.student, i.student_name, i.student_batch, r.book_title,
			if(r.is_billable, %(billed)s, %(free)s) billing, r.qty, ifnull(r.returned_qty, 0) returned_qty, r.rate,
			r.amount, i.sales_invoice, i.stock_entry, i.issued_by
		from `tabLibrary Book Issuance` i join `tabLibrary Book Issuance Item` r on r.parent = i.name
		where i.docstatus = 1 {conds} order by i.posting_date, i.name, r.idx
	""", dict(values, billed=_("Billed"), free=_("Free")), as_dict=True)
	return columns(), data


def columns():
	return [
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 95},
		{"fieldname": "issuance", "label": _("Issuance"), "fieldtype": "Link", "options": "Library Book Issuance", "width": 140},
		{"fieldname": "student", "label": _("Student"), "fieldtype": "Link", "options": "Student", "width": 100},
		{"fieldname": "student_name", "label": _("Student Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "student_batch", "label": _("Class"), "fieldtype": "Data", "width": 70},
		{"fieldname": "book_title", "label": _("Book"), "fieldtype": "Data", "width": 180},
		{"fieldname": "billing", "label": _("Billing"), "fieldtype": "Data", "width": 70},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 60},
		{"fieldname": "returned_qty", "label": _("Returned"), "fieldtype": "Float", "width": 75},
		{"fieldname": "rate", "label": _("Rate"), "fieldtype": "Currency", "width": 90},
		{"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "width": 100},
		{"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 150},
		{"fieldname": "stock_entry", "label": _("Stock Entry"), "fieldtype": "Link", "options": "Stock Entry", "width": 140},
		{"fieldname": "issued_by", "label": _("Issued By"), "fieldtype": "Link", "options": "User", "width": 150},
	]
