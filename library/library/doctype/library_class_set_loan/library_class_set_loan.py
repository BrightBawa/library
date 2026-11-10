# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt
"""A teacher borrows many copies of lending books for a class. Copies are allocated on submit and
count as on loan; returns and losses are recorded per book line. Never billed."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate, today

from library.library import reservations
from library.library.stats import update_book_stats


class LibraryClassSetLoan(Document):
	def validate(self):
		teacher = frappe.db.get_value("Library Member", self.teacher,
			["reference_doctype", "membership_status", "full_name"], as_dict=True)
		if not teacher or teacher.reference_doctype != "Employee":
			frappe.throw(_("Class sets are lent to teachers: choose a Library Member linked to an Employee."))
		if teacher.membership_status != "Active":
			frappe.throw(_("{0}'s library membership is {1}.").format(teacher.full_name, teacher.membership_status))
		if getdate(self.due_date) < getdate(self.issue_date):
			frappe.throw(_("The due date cannot be before the issue date."))
		for row in self.items:
			if frappe.db.get_value("Library Book", row.book, "book_type") != "Lending":
				frappe.throw(_("Row {0}: class sets are made of lending books.").format(row.idx))
			if cint(row.qty) < 1:
				frappe.throw(_("Row {0}: lend at least one copy.").format(row.idx))
		if self.docstatus == 0:
			self.status = "Draft"

	def before_submit(self):
		wanted = {}
		for row in self.items:
			wanted[row.book] = wanted.get(row.book, 0) + cint(row.qty)
		for book, qty in wanted.items():
			available = frappe.db.count("Library Book Copy", {"book": book, "status": "Available"})
			if available < qty:
				frappe.throw(_("{0}: {1} copies wanted, {2} on the shelf.").format(
					frappe.db.get_value("Library Book", book, "book_title"), qty, available))

	def on_submit(self):
		for row in self.items:
			copies = frappe.get_all("Library Book Copy", filters={"book": row.book, "status": "Available"},
				fields=["name", "book_title"], order_by="name", limit=cint(row.qty))
			for copy in copies:
				frappe.db.set_value("Library Book Copy", copy.name, "status", "Issued")
				child = self.append("copies", {"copy": copy.name, "book": row.book, "book_title": copy.book_title,
					"state": "On Loan", "item_row": row.name})
				child.docstatus = 1
				child.db_insert()
			update_book_stats(row.book)
		self.update_status()

	def line(self, item_row):
		row = next((r for r in self.items if r.name == item_row), None)
		if not row:
			frappe.throw(_("That book line is not on this loan."))
		return row

	def take(self, item_row, qty, copies, new_state):
		self.check_permission("submit")
		if self.docstatus != 1:
			frappe.throw(_("Only a submitted class set loan can be updated."))
		row = self.line(item_row)
		on_loan = [c for c in self.copies if c.item_row == item_row and c.state == "On Loan"]
		if copies:
			chosen = [c for c in on_loan if c.copy in set(frappe.parse_json(copies))]
		else:
			chosen = on_loan[:cint(qty)]
		if not chosen or (qty and len(chosen) < cint(qty)):
			frappe.throw(_("Only {0} copies of {1} are still on loan.").format(len(on_loan), row.book_title))
		for copy in chosen:
			copy.db_set("state", new_state, update_modified=False)
			frappe.db.set_value("Library Book Copy", copy.copy, "status", "Available" if new_state == "Returned" else "Lost")
		field = "returned_qty" if new_state == "Returned" else "lost_qty"
		row.db_set(field, cint(row.get(field)) + len(chosen), update_modified=False)
		update_book_stats(row.book)
		if new_state == "Returned":
			reservations.notify_next(row.book)
		self.update_status()
		return len(chosen)

	@frappe.whitelist()
	def return_copies(self, item_row, qty=None, copies=None):
		return self.take(item_row, qty, copies, "Returned")

	@frappe.whitelist()
	def mark_lost(self, item_row, qty=None, copies=None):
		return self.take(item_row, qty, copies, "Lost")

	def update_status(self):
		outstanding = sum(cint(r.qty) - cint(r.returned_qty) - cint(r.lost_qty) for r in self.items)
		settled = sum(cint(r.returned_qty) + cint(r.lost_qty) for r in self.items)
		lost = sum(cint(r.lost_qty) for r in self.items)
		if self.docstatus == 2:
			status = "Cancelled"
		elif self.docstatus == 0:
			status = "Draft"
		elif outstanding <= 0:
			status = "Closed" if lost else "Returned"
		elif getdate(self.due_date) < getdate(today()):
			status = "Overdue"
		elif settled:
			status = "Partly Returned"
		else:
			status = "Open"
		if status != self.status:
			self.db_set("status", status, update_modified=False)

	def before_cancel(self):
		if any(c.state != "On Loan" for c in self.copies):
			frappe.throw(_("Some copies are already returned or lost; record the rest as returned instead of cancelling."))

	def on_cancel(self):
		for copy in self.copies:
			frappe.db.set_value("Library Book Copy", copy.copy, "status", "Available")
		for book in {r.book for r in self.items}:
			update_book_stats(book)
		self.update_status()


def refresh_statuses():
	"""Daily: loans past their due date become Overdue."""
	for name in frappe.get_all("Library Class Set Loan",
			filters={"docstatus": 1, "status": ["in", ["Open", "Partly Returned"]], "due_date": ["<", today()]}, pluck="name"):
		frappe.get_doc("Library Class Set Loan", name).update_status()
