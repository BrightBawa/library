# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt
"""Loans of lending copies.

An Issue opens a loan. A Return closes it and a Renew extends it; both are their own
submitted documents whose ``against_issue`` points at the Issue. Only this controller
writes the Issue's loan state (return_date, due_date, renewal_count, days_overdue,
fine_amount) after it is submitted. ``library.api.circulation`` goes through here too.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, flt, getdate, today

from library.library import billing, fines, reservations
from library.library.stats import OPEN_LOAN, update_book_stats, update_member_stats


class LibraryCirculation(Document):
	# A rental invoice is cancelled by on_cancel; do not ask the user to cancel it first.
	ignore_linked_doctypes = ("Sales Invoice",)

	def validate(self):
		self.librarian = self.librarian or frappe.session.user
		self.transaction_date = self.transaction_date or today()
		if self.transaction_type == "Issue":
			self.validate_issue()
		else:
			issue = self.get_open_issue()
			if self.transaction_type == "Return":
				self.validate_return(issue)
			else:
				self.validate_renewal(issue)

	def validate_issue(self):
		# validate runs before Frappe's mandatory check, so say plainly what is missing.
		if not self.member or not self.book_copy:
			frappe.throw(_("Select the member and the book copy to issue."))
		self.against_issue = None
		member = frappe.get_doc("Library Member", self.member)
		validate_member_can_borrow(member)

		status, book = frappe.db.get_value("Library Book Copy", self.book_copy, ["status", "book"])
		reserved_for_member = frappe.db.exists(
			"Library Reservation", {"book": book, "member": self.member, "status": "Active"}
		)
		if status == "Reserved" and not reserved_for_member:
			frappe.throw(_("Copy {0} is held for another member's reservation.").format(self.book_copy))
		if status not in ("Available", "Reserved"):
			frappe.throw(_("Copy {0} is not available; its status is {1}.").format(self.book_copy, status))
		if not reserved_for_member and reservations.other_members_waiting(book, self.member):
			frappe.msgprint(_("Other members are waiting for this book."), indicator="orange", alert=True)

		limit = max_books(member)
		on_loan = frappe.db.count("Library Circulation", dict(OPEN_LOAN, member=self.member))
		if on_loan >= limit:
			frappe.throw(_("{0} already has {1} books on loan, the limit for membership type {2}.").format(
				member.full_name, on_loan, member.membership_type))

		self.issue_date = self.transaction_date
		self.due_date = self.due_date or add_days(self.issue_date, loan_period(member))
		if getdate(self.due_date) < getdate(self.issue_date):
			frappe.throw(_("The due date cannot be before the issue date."))
		self.max_renewals_allowed = cint(frappe.db.get_single_value("Library Settings", "max_renewals"))
		self.renewal_count = 0
		self.return_date = None
		self.days_overdue = 0
		self.fine_amount = 0
		if flt(self.rental_fee) < 0:
			frappe.throw(_("The rental fee cannot be negative."))
		if flt(self.rental_fee) and not billing.member_customer(self.member):
			frappe.throw(_("Rental fees are billed to a student's Customer; {0} has none.").format(member.full_name))

	def get_open_issue(self):
		if not self.book_copy:
			frappe.throw(_("Select the book copy being returned or renewed."))
		name = frappe.db.get_value("Library Circulation", dict(OPEN_LOAN, book_copy=self.book_copy))
		if not name:
			frappe.throw(_("Copy {0} is not on loan.").format(self.book_copy))
		issue = frappe.get_doc("Library Circulation", name)
		if self.member and self.member != issue.member:
			frappe.throw(_("Copy {0} is on loan to {1}, not to {2}.").format(
				self.book_copy, issue.member_name or issue.member, self.member_name or self.member))
		self.member = issue.member
		self.member_name = issue.member_name
		self.rental_fee = 0
		self.against_issue = issue.name
		self.issue_date = issue.issue_date
		self.max_renewals_allowed = issue.max_renewals_allowed
		return issue

	def validate_return(self, issue):
		self.return_date = self.return_date or self.transaction_date
		if getdate(self.return_date) < getdate(issue.issue_date):
			frappe.throw(_("The return date cannot be before the issue date {0}.").format(
				frappe.utils.formatdate(issue.issue_date)))
		self.due_date = issue.due_date
		self.renewal_count = issue.renewal_count
		self.days_overdue = fines.days_overdue(issue.due_date, self.return_date)
		self.fine_amount = (
			self.days_overdue * fines.fine_per_day(self.member) if fines.fines_enabled() else 0
		)

	def validate_renewal(self, issue):
		if cint(issue.renewal_count) >= cint(issue.max_renewals_allowed):
			frappe.throw(_("This loan has been renewed {0} times, the maximum allowed.").format(
				cint(issue.renewal_count)))
		if reservations.other_members_waiting(issue.book, issue.member):
			frappe.throw(_("Another member has reserved this book, so the loan cannot be renewed."))
		member = frappe.get_doc("Library Member", issue.member)
		validate_member_can_borrow(member)
		self.original_due_date = issue.due_date
		start = max(getdate(issue.due_date), getdate(self.transaction_date))
		self.due_date = add_days(start, loan_period(member))
		self.renewal_count = cint(issue.renewal_count) + 1
		self.return_date = None
		self.days_overdue = 0
		self.fine_amount = 0

	def on_submit(self):
		if self.transaction_type == "Issue":
			frappe.db.set_value("Library Book Copy", self.book_copy, "status", "Issued")
			reservations.fulfil(self.member, self.get_book(), self.name)
			if flt(self.rental_fee) > 0:
				self.db_set("sales_invoice", billing.bill_rental(self))
		elif self.transaction_type == "Return":
			self.close_loan()
		else:
			issue = frappe.get_doc("Library Circulation", self.against_issue)
			issue.db_set({"due_date": self.due_date, "renewal_count": self.renewal_count},
				update_modified=False)
		self.update_stats()

	def close_loan(self):
		issue = frappe.get_doc("Library Circulation", self.against_issue)
		issue.db_set({"return_date": self.return_date, "days_overdue": self.days_overdue},
			update_modified=False)
		fine = fines.sync_overdue_fine(issue, as_of=self.return_date)
		issue.db_set("fine_amount", fine.fine_amount if fine else 0, update_modified=False)

		copy = {"status": "Available"}
		if self.condition_on_return in ("Damaged", "Lost"):
			copy["status"] = self.condition_on_return
		if self.condition_on_return and self.condition_on_return != "Lost":
			copy["condition"] = self.condition_on_return
		frappe.db.set_value("Library Book Copy", self.book_copy, copy)
		condition_fine = fines.condition_fine(self)
		for final in (fine, condition_fine):  # both are final now
			if final:
				billing.bill_fine(final)
		if copy["status"] == "Available":
			reservations.notify_next(self.get_book())

	def before_cancel(self):
		if self.transaction_type == "Issue":
			billing.assert_unpaid(self.sales_invoice)
			later = frappe.db.get_value("Library Circulation",
				{"against_issue": self.name, "docstatus": 1}, ["name", "transaction_type"], as_dict=True)
			if later:
				frappe.throw(_("Cancel {0} {1} first; it was made against this Issue.").format(
					later.transaction_type, later.name))
		elif self.transaction_type == "Return":
			if frappe.db.exists("Library Circulation", dict(OPEN_LOAN, book_copy=self.book_copy)):
				frappe.throw(_("Copy {0} has been issued again since this return.").format(self.book_copy))
		elif self.transaction_type == "Renew":
			later = frappe.db.exists("Library Circulation", {
				"against_issue": self.against_issue, "docstatus": 1,
				"name": ["!=", self.name], "creation": [">", self.creation],
			})
			if later:
				frappe.throw(_("Cancel {0} first; it was made after this renewal.").format(later))

	def on_cancel(self):
		if self.transaction_type == "Issue":
			billing.cancel_document("Sales Invoice", self.sales_invoice)
			frappe.db.set_value("Library Book Copy", self.book_copy, "status", "Available")
			fines.remove_unsettled_fines(self.name)
			fulfilled = frappe.db.get_value("Library Reservation", {"circulation": self.name})
			if fulfilled:
				frappe.db.set_value("Library Reservation", fulfilled,
					{"status": "Active", "fulfilled_date": None, "circulation": None})
		elif self.transaction_type == "Return":
			fines.remove_unsettled_fines(self.name)
			issue = frappe.get_doc("Library Circulation", self.against_issue)
			issue.db_set({"return_date": None, "days_overdue": fines.days_overdue(issue.due_date)},
				update_modified=False)
			issue.reload()
			fine = fines.sync_overdue_fine(issue)
			issue.db_set("fine_amount", fine.fine_amount if fine else 0, update_modified=False)
			frappe.db.set_value("Library Book Copy", self.book_copy, "status", "Issued")
		else:
			issue = frappe.get_doc("Library Circulation", self.against_issue)
			issue.db_set({"due_date": self.original_due_date,
				"renewal_count": max(cint(issue.renewal_count) - 1, 0)}, update_modified=False)
		self.update_stats()

	def get_book(self):
		return self.book or frappe.db.get_value("Library Book Copy", self.book_copy, "book")

	def update_stats(self):
		update_book_stats(self.get_book())
		update_member_stats(self.member)


def validate_member_can_borrow(member):
	if member.membership_status != "Active":
		frappe.throw(_("{0}'s membership is {1}.").format(
			member.full_name, member.membership_status or _("not set")))
	if member.membership_end_date and getdate(member.membership_end_date) < getdate(today()):
		frappe.throw(_("{0}'s membership ended on {1}.").format(
			member.full_name, frappe.utils.formatdate(member.membership_end_date)))


def loan_period(member):
	days = cint(frappe.db.get_value("Library Membership Type", member.membership_type, "loan_period_days"))
	return days or cint(frappe.db.get_single_value("Library Settings", "default_loan_period")) or 14


def max_books(member):
	limit = cint(frappe.db.get_value("Library Membership Type", member.membership_type, "max_books_allowed"))
	return limit or 3


@frappe.whitelist()
def get_open_issue(book_copy):
	"""For the form: the member and Issue a Return or Renew applies to."""
	frappe.has_permission("Library Circulation", "read", throw=True)
	name = frappe.db.get_value("Library Circulation", dict(OPEN_LOAN, book_copy=book_copy))
	if not name:
		return None
	return frappe.db.get_value("Library Circulation", name,
		["name", "member", "member_name", "issue_date", "due_date", "renewal_count"], as_dict=True)
