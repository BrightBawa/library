# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt
"""Books sent back from a submitted issuance (wrong book, unused). Billed books are credited on a
credit note against the original invoice; free books come back through a Material Receipt."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from library.library import billing
from library.library.stock import refresh_books_for_items

MANAGER_ROLES = {"Library Manager"}


def require_library_manager(action):
	if frappe.session.user != "Administrator" and not MANAGER_ROLES & set(frappe.get_roles()):
		frappe.throw(_("Only a Library Manager can {0}.").format(action), frappe.PermissionError)


def returned_quantities(issuance, exclude=None):
	"""{issuance row name: qty returned} over the submitted returns of an issuance."""
	return dict(frappe.db.sql("""
		select r.issuance_item, sum(r.qty) from `tabLibrary Issuance Return` x
		join `tabLibrary Issuance Return Item` r on r.parent = x.name
		where x.docstatus = 1 and x.against_issuance = %s and x.name != %s group by r.issuance_item""",
		(issuance, exclude or "")))


@frappe.whitelist()
def get_returnable_items(issuance):
	"""Rows of an issuance that still have books to return, for the form."""
	doc = frappe.get_doc("Library Book Issuance", issuance)
	doc.check_permission("read")
	returned = returned_quantities(issuance)
	rows = []
	for row in doc.items:
		left = flt(row.qty) - flt(returned.get(row.name))
		if left > 0:
			rows.append({"issuance_item": row.name, "book": row.book, "book_title": row.book_title, "item": row.item,
				"is_billable": row.is_billable, "rate": row.rate, "max_qty": left, "qty": left})
	return rows


class LibraryIssuanceReturn(Document):
	ignore_linked_doctypes = ("Sales Invoice", "Stock Entry")

	def validate(self):
		issuance = frappe.get_doc("Library Book Issuance", self.against_issuance)
		if issuance.docstatus != 1:
			frappe.throw(_("Books can only be returned from a submitted issuance."))
		self.student, self.student_name = issuance.student, issuance.student_name
		self.customer, self.company, self.currency = issuance.customer, issuance.company, issuance.currency
		source = {row.name: row for row in issuance.items}
		returned = returned_quantities(issuance.name, exclude=self.name)
		if not self.items:
			frappe.throw(_("Add the books being returned."))
		for row in self.items:
			src = source.get(row.issuance_item)
			if not src:
				frappe.throw(_("Row {0} is not a book of issuance {1}.").format(row.idx, issuance.name))
			row.book, row.book_title, row.item = src.book, src.book_title, src.item
			row.is_billable, row.rate = src.is_billable, src.rate
			row.max_qty = flt(src.qty) - flt(returned.get(src.name))
			if flt(row.qty) <= 0 or flt(row.qty) > row.max_qty:
				frappe.throw(_("Row {0}: {1} can be returned at most {2} more times.").format(
					row.idx, row.book_title, f"{row.max_qty:g}"))
			row.amount = flt(row.qty) * flt(row.rate) if row.is_billable else 0
			row.currency = self.currency
		self.total_billable_qty = sum(flt(r.qty) for r in self.items if r.is_billable)
		self.total_billable = sum(flt(r.amount) for r in self.items if r.is_billable)
		self.total_free = sum(flt(r.qty) for r in self.items if not r.is_billable)

	def before_submit(self):
		require_library_manager(_("approve a return"))
		self.returned_by = frappe.session.user

	def on_submit(self):
		issuance = frappe.get_doc("Library Book Issuance", self.against_issuance)
		remarks = _("Library Issuance Return {0} against {1} ({2})").format(self.name, issuance.name, self.reason)
		billed = {}
		for row in self.items:
			if row.is_billable:
				billed[row.item] = billed.get(row.item, 0) + flt(row.qty)
		if billed:
			credit = billing.make_credit_note(original_invoice=issuance.sales_invoice, quantities=billed,
				posting_date=self.posting_date, issuance=issuance.name, document=self, remarks=remarks)
			self.db_set("sales_invoice_return", credit.name)
		free = [r for r in self.items if not r.is_billable]
		if free:
			entry = billing.make_stock_entry(purpose="Material Receipt", company=self.company,
				posting_date=self.posting_date, issuance=issuance.name, document=self, remarks=remarks,
				rows=[{"item_code": r.item, "qty": r.qty, "basic_rate": issue_rate(issuance.stock_entry, r.item)} for r in free])
			self.db_set("stock_entry", entry.name)
		self.update_issuance()

	def before_cancel(self):
		require_library_manager(_("cancel a return"))
		billing.assert_unpaid(self.sales_invoice_return)

	def on_cancel(self):
		billing.cancel_document("Sales Invoice", self.sales_invoice_return)
		billing.cancel_document("Stock Entry", self.stock_entry)
		self.update_issuance()

	def update_issuance(self):
		returned = returned_quantities(self.against_issuance)
		for row in self.items:
			frappe.db.set_value("Library Book Issuance Item", row.issuance_item, "returned_qty",
				flt(returned.get(row.issuance_item)), update_modified=False)
		refresh_books_for_items({r.item for r in self.items})


def issue_rate(stock_entry, item):
	"""The rate a free book left the library at, so it comes back at the same cost."""
	if not stock_entry:
		return 0
	return flt(frappe.db.get_value("Stock Entry Detail", {"parent": stock_entry, "item_code": item}, "valuation_rate"))
