# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt
"""Values for the library's custom number cards (each returns {"value", "fieldtype"})."""

import frappe
from frappe.utils import flt, get_first_day, get_last_day, today

from library.library import school
from library.library.stats import OPEN_LOAN


def _card(value, fieldtype="Int"):
	return {"value": flt(value) if fieldtype == "Currency" else int(flt(value)), "fieldtype": fieldtype}


def _require(doctype):
	frappe.has_permission(doctype, "read", throw=True)


def term_dates():
	"""(start, end) of the current academic term, else of the current academic year."""
	term = school.current_academic_term()
	if term:
		return term.term_start_date, term.term_end_date
	year = school.current_academic_year()
	if year:
		return frappe.db.get_value("Academic Year", year, ["year_start_date", "year_end_date"])
	return today(), today()


def _issuances_between(start, end, field):
	return flt(frappe.db.sql(f"""
		select coalesce(sum(`{field}`), 0) from `tabLibrary Book Issuance`
		where docstatus = 1 and posting_date between %s and %s""", (start, end))[0][0])


@frappe.whitelist()
def books_in_stock(filters=None):
	"""Issue-type books in the library warehouse plus lending copies on the shelf."""
	_require("Library Book")
	warehouse = frappe.db.get_single_value("Library Settings", "library_warehouse")
	issue = flt(frappe.db.sql("""
		select coalesce(sum(b.actual_qty), 0) from tabBin b
		join `tabLibrary Book` lb on lb.item = b.item_code and lb.book_type = 'Issue'
		where b.warehouse = %s""", warehouse)[0][0]) if warehouse else 0
	lending = frappe.db.count("Library Book Copy", {"status": "Available"})
	return _card(issue + lending)


@frappe.whitelist()
def copies_on_loan(filters=None):
	"""Lending copies out on loan, to members or on class set loans."""
	_require("Library Book Copy")
	return _card(frappe.db.count("Library Book Copy", {"status": "Issued"}))


@frappe.whitelist()
def overdue_loans(filters=None):
	_require("Library Circulation")
	loans = frappe.db.count("Library Circulation", dict(OPEN_LOAN, due_date=["<", today()]))
	if frappe.db.exists("DocType", "Library Class Set Loan"):
		loans += frappe.db.count("Library Class Set Loan", {"docstatus": 1, "status": "Overdue"})
	return _card(loans)


@frappe.whitelist()
def issuances_this_month(filters=None):
	_require("Library Book Issuance")
	return _card(frappe.db.count("Library Book Issuance", {
		"docstatus": 1, "posting_date": ["between", [get_first_day(today()), get_last_day(today())]]}))


@frappe.whitelist()
def billed_this_term(filters=None):
	"""Amount billed on issuances this term, less what Issuance Returns credited back."""
	_require("Library Book Issuance")
	start, end = term_dates()
	billed = _issuances_between(start, end, "total_billable")
	if frappe.db.exists("DocType", "Library Issuance Return"):
		billed -= flt(frappe.db.sql("""select coalesce(sum(total_billable), 0) from `tabLibrary Issuance Return`
			where docstatus = 1 and posting_date between %s and %s""", (start, end))[0][0])
	return _card(billed, "Currency")


@frappe.whitelist()
def free_books_this_term(filters=None):
	_require("Library Book Issuance")
	start, end = term_dates()
	free = _issuances_between(start, end, "total_free")
	if frappe.db.exists("DocType", "Library Issuance Return"):
		free -= flt(frappe.db.sql("""select coalesce(sum(total_free), 0) from `tabLibrary Issuance Return`
			where docstatus = 1 and posting_date between %s and %s""", (start, end))[0][0])
	return _card(free)


@frappe.whitelist()
def active_members(filters=None):
	_require("Library Member")
	return _card(frappe.db.count("Library Member", {"membership_status": "Active"}))


@frappe.whitelist()
def unpaid_fines(filters=None):
	_require("Library Fine")
	return _card(frappe.db.sql("""select coalesce(sum(outstanding_amount), 0) from `tabLibrary Fine`
		where payment_status in ('Unpaid', 'Partially Paid')""")[0][0], "Currency")


@frappe.whitelist()
def get_overdue_books_count():
	"""Kept for the old "Overdue Books" card until the patch removes it."""
	return overdue_loans()["value"]
