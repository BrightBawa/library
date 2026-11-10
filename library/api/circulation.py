"""Library circulation API and daily jobs.

issue_book / return_book / renew_book create and submit Library Circulation documents,
so the controller's rules, copy status, fines and counters apply exactly as they do in
the form. Permission checks are the normal create/submit checks of that DocType.
"""

import frappe
from frappe import _
from frappe.utils import getdate, today

from library.library import fines, reservations
from library.library.stats import OPEN_LOAN, members_with_open_loans, update_member_stats


def _submit(values):
	doc = frappe.get_doc({"doctype": "Library Circulation", **values})
	doc.insert()
	doc.submit()
	return doc.name


def _issue(circulation):
	issue = frappe.get_doc("Library Circulation", frappe.utils.cstr(circulation).strip())
	if issue.transaction_type != "Issue" or issue.docstatus != 1:
		frappe.throw(_("{0} is not a submitted Issue.").format(issue.name))
	if issue.return_date:
		frappe.throw(_("This book has already been returned."))
	return issue


@frappe.whitelist()
def issue_book(member, book_copy, issue_date=None, due_date=None):
	"""Issue a copy to a member; returns the Issue's name."""
	return _submit({
		"transaction_type": "Issue",
		"transaction_date": getdate(issue_date) if issue_date else today(),
		"member": member,
		"book_copy": book_copy,
		"due_date": getdate(due_date) if due_date else None,
	})


@frappe.whitelist()
def return_book(circulation, return_date=None, condition=None):
	"""Return the copy of an open Issue; returns the Return's name."""
	issue = _issue(circulation)
	return _submit({
		"transaction_type": "Return",
		"transaction_date": today(),
		"return_date": getdate(return_date) if return_date else today(),
		"member": issue.member,
		"book_copy": issue.book_copy,
		"condition_on_return": condition,
	})


@frappe.whitelist()
def renew_book(circulation):
	"""Renew an open Issue; returns the Renew's name."""
	issue = _issue(circulation)
	return _submit({
		"transaction_type": "Renew",
		"transaction_date": today(),
		"member": issue.member,
		"book_copy": issue.book_copy,
	})


def _open_overdue_loans():
	return frappe.get_all(
		"Library Circulation",
		filters=dict(OPEN_LOAN, due_date=["<", today()]),
		fields=["name", "member", "member_name", "book", "book_title", "book_copy", "due_date"],
	)


def send_overdue_reminders():
	"""Kept for jobs queued under this path; the daily job is library.library.notifications."""
	from library.library.notifications import send_overdue_reminders as send

	return send()


def auto_calculate_fines():
	"""Daily: bring each open loan's days overdue and Overdue fine up to date, then the counters."""
	for loan in _open_overdue_loans():
		issue = frappe.get_doc("Library Circulation", loan.name)
		issue.db_set("days_overdue", fines.days_overdue(issue.due_date), update_modified=False)
		fine = fines.sync_overdue_fine(issue)
		issue.db_set("fine_amount", fine.fine_amount if fine else 0, update_modified=False)
	for member in members_with_open_loans():
		update_member_stats(member)


def expire_unclaimed_reservations():
	"""Daily: expire reservations not collected by their expiry date; notify the next member."""
	# "is set" matters: Frappe compares an empty date as the earliest date, so without it
	# every reservation not yet notified (no expiry date) would be expired too.
	expired = frappe.get_all(
		"Library Reservation",
		filters=[["status", "=", "Active"], ["expiry_date", "is", "set"], ["expiry_date", "<", today()]],
		fields=["name", "book"],
		order_by="expiry_date asc, creation asc",
	)
	for reservation in expired:
		frappe.db.set_value("Library Reservation", reservation.name, "status", "Expired")
		reservations.notify_next(reservation.book)
	return len(expired)
