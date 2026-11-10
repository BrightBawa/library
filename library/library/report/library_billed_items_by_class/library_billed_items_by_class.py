# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

from library.library import school
from library.library.reporting import date_conditions, has_returns


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.academic_year = filters.academic_year or school.current_academic_year()
	conds, values = date_conditions(filters, "i.posting_date", "i.academic_year")
	totals = {}
	for batch, book, qty, amount in frappe.db.sql(f"""
			select ifnull(i.student_batch, ''), r.book_title, sum(r.qty), sum(r.amount)
			from `tabLibrary Book Issuance` i join `tabLibrary Book Issuance Item` r on r.parent = i.name
			where i.docstatus = 1 and r.is_billable = 1 {conds} group by i.student_batch, r.book_title""", values):
		totals[(batch, book)] = [flt(qty), flt(amount)]
	if has_returns():
		for batch, book, qty, amount in frappe.db.sql(f"""
				select ifnull(i.student_batch, ''), r.book_title, sum(r.qty), sum(r.amount)
				from `tabLibrary Issuance Return` x join `tabLibrary Issuance Return Item` r on r.parent = x.name
				join `tabLibrary Book Issuance` i on i.name = x.against_issuance
				where x.docstatus = 1 and r.is_billable = 1 {conds} group by i.student_batch, r.book_title""", values):
			row = totals.setdefault((batch, book), [0, 0])
			row[0] -= flt(qty)
			row[1] -= flt(amount)
	data = [{"student_batch": batch or _("No class"), "book_title": book, "qty": qty, "amount": amount}
		for (batch, book), (qty, amount) in sorted(totals.items())]
	return columns(), data


def columns():
	return [
		{"fieldname": "student_batch", "label": _("Class"), "fieldtype": "Data", "width": 110},
		{"fieldname": "book_title", "label": _("Book"), "fieldtype": "Data", "width": 240},
		{"fieldname": "qty", "label": _("Qty Billed"), "fieldtype": "Float", "width": 100},
		{"fieldname": "amount", "label": _("Amount Billed"), "fieldtype": "Currency", "width": 130},
	]
