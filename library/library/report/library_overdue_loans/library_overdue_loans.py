# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import date_diff, today

from library.library.stats import OPEN_LOAN


def execute(filters=None):
	data = []
	for loan in frappe.get_all("Library Circulation", filters=dict(OPEN_LOAN, due_date=["<", today()]),
			fields=["name", "member", "member_name", "book_title", "book_copy", "issue_date", "due_date", "fine_amount"],
			order_by="due_date asc"):
		member = frappe.db.get_value("Library Member", loan.member, ["reference_doctype", "email"], as_dict=True) or {}
		data.append(dict(loan, document_type="Library Circulation", member_type=member.get("reference_doctype"),
			email=member.get("email"), days_overdue=date_diff(today(), loan.due_date), qty=1))
	if frappe.db.exists("DocType", "Library Class Set Loan"):
		for row in frappe.db.sql("""
				select l.name, l.teacher member, l.teacher_name member_name, i.book_title, l.issue_date, l.due_date,
					i.qty - ifnull(i.returned_qty, 0) - ifnull(i.lost_qty, 0) qty
				from `tabLibrary Class Set Loan` l join `tabLibrary Class Set Loan Item` i on i.parent = l.name
				where l.docstatus = 1 and l.due_date < %s and i.qty - ifnull(i.returned_qty, 0) - ifnull(i.lost_qty, 0) > 0
				order by l.due_date""", today(), as_dict=True):
			data.append(dict(row, document_type="Library Class Set Loan", member_type=_("Class set"),
				email=frappe.db.get_value("Library Member", row.member, "email"), days_overdue=date_diff(today(), row.due_date),
				fine_amount=0, book_copy=None))
	return columns(), data


def columns():
	return [
		{"fieldname": "document_type", "label": _("Document Type"), "fieldtype": "Data", "hidden": 1},
		{"fieldname": "name", "label": _("Loan"), "fieldtype": "Dynamic Link", "options": "document_type", "width": 140},
		{"fieldname": "member", "label": _("Member"), "fieldtype": "Link", "options": "Library Member", "width": 110},
		{"fieldname": "member_name", "label": _("Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "member_type", "label": _("Type"), "fieldtype": "Data", "width": 80},
		{"fieldname": "book_title", "label": _("Book"), "fieldtype": "Data", "width": 180},
		{"fieldname": "book_copy", "label": _("Copy"), "fieldtype": "Link", "options": "Library Book Copy", "width": 120},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 55},
		{"fieldname": "issue_date", "label": _("Issued"), "fieldtype": "Date", "width": 95},
		{"fieldname": "due_date", "label": _("Due"), "fieldtype": "Date", "width": 95},
		{"fieldname": "days_overdue", "label": _("Days Overdue"), "fieldtype": "Int", "width": 95},
		{"fieldname": "fine_amount", "label": _("Fine So Far"), "fieldtype": "Currency", "width": 100},
		{"fieldname": "email", "label": _("Email"), "fieldtype": "Data", "width": 170},
	]
