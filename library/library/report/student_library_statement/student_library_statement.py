# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

from library.library.reporting import date_conditions, has_returns


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.student:
		return columns(), []
	rows = issued(filters) + returned(filters) + fines_and_rentals(filters)
	rows.sort(key=lambda r: (r["date"], r["document"] or ""))
	return columns(), rows


def columns():
	return [
		{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "entry", "label": _("Entry"), "fieldtype": "Data", "width": 150},
		{"fieldname": "document_type", "label": _("Document Type"), "fieldtype": "Data", "hidden": 1},
		{"fieldname": "document", "label": _("Document"), "fieldtype": "Dynamic Link", "options": "document_type", "width": 160},
		{"fieldname": "detail", "label": _("Book / Detail"), "fieldtype": "Data", "width": 220},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 70},
		{"fieldname": "amount", "label": _("Amount Billed"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "sales_invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 160},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 110},
	]


def issued(filters):
	conds, values = date_conditions(filters, "i.posting_date", "i.academic_year")
	values["student"] = filters.student
	return [{
		"date": r.posting_date, "entry": _("Issued, billed") if r.is_billable else _("Issued, free"),
		"document_type": "Library Book Issuance", "document": r.name, "detail": r.book_title, "qty": r.qty,
		"amount": r.amount if r.is_billable else 0, "sales_invoice": r.sales_invoice if r.is_billable else None,
		"status": _("Submitted")}
		for r in frappe.db.sql(f"""select i.posting_date, i.name, i.sales_invoice, r.book_title, r.qty, r.amount, r.is_billable
			from `tabLibrary Book Issuance` i join `tabLibrary Book Issuance Item` r on r.parent = i.name
			where i.docstatus = 1 and i.student = %(student)s {conds}""", values, as_dict=True)]


def returned(filters):
	if not has_returns():
		return []
	conds, values = date_conditions(filters, "x.posting_date", "i.academic_year")
	values["student"] = filters.student
	return [{
		"date": r.posting_date, "entry": _("Returned, billed") if r.is_billable else _("Returned, free"),
		"document_type": "Library Issuance Return", "document": r.name, "detail": r.book_title, "qty": -flt(r.qty),
		"amount": -flt(r.amount) if r.is_billable else 0, "sales_invoice": r.sales_invoice_return if r.is_billable else None,
		"status": _("Submitted")}
		for r in frappe.db.sql(f"""select x.posting_date, x.name, x.sales_invoice_return, r.book_title, r.qty, r.amount, r.is_billable
			from `tabLibrary Issuance Return` x join `tabLibrary Issuance Return Item` r on r.parent = x.name
			join `tabLibrary Book Issuance` i on i.name = x.against_issuance
			where x.docstatus = 1 and i.student = %(student)s {conds}""", values, as_dict=True)]


def fines_and_rentals(filters):
	members = frappe.get_all("Library Member", filters={"student": filters.student}, pluck="name")
	if not members:
		return []
	rows = []
	conds, values = date_conditions(filters, "f.fine_date")
	values["members"] = members
	for f in frappe.db.sql(f"""select f.fine_date, f.name, f.fine_type, f.fine_amount, f.payment_status, f.sales_invoice
			from `tabLibrary Fine` f where f.member in %(members)s {conds}""", values, as_dict=True):
		rows.append({"date": f.fine_date, "entry": _("{0} fine").format(_(f.fine_type)), "document_type": "Library Fine",
			"document": f.name, "detail": "", "qty": None, "amount": f.fine_amount if f.payment_status == "Invoiced" else 0,
			"sales_invoice": f.sales_invoice, "status": _(f.payment_status)})
	conds, values = date_conditions(filters, "c.transaction_date")
	values["members"] = members
	for c in frappe.db.sql(f"""select c.transaction_date, c.name, c.book_title, c.rental_fee, c.sales_invoice
			from `tabLibrary Circulation` c where c.docstatus = 1 and c.transaction_type = 'Issue'
			and c.rental_fee > 0 and c.member in %(members)s {conds}""", values, as_dict=True):
		rows.append({"date": c.transaction_date, "entry": _("Rental"), "document_type": "Library Circulation",
			"document": c.name, "detail": c.book_title, "qty": 1, "amount": c.rental_fee, "sales_invoice": c.sales_invoice,
			"status": _("Billed")})
	return rows
