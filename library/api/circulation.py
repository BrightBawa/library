"""Library circulation API and daily jobs.

issue_book / return_book / renew_book create and submit Library Circulation documents,
so the controller's rules, copy status, fines and counters apply exactly as they do in
the form. Permission checks are the normal create/submit checks of that DocType.
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate, today

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
	"""Daily: email members whose loan is at least `overdue_reminder_days` overdue."""
	if not cint(frappe.db.get_single_value("Library Settings", "send_overdue_reminders")):
		return 0
	after = cint(frappe.db.get_single_value("Library Settings", "overdue_reminder_days")) or 1
	sent = 0
	for loan in _open_overdue_loans():
		days = fines.days_overdue(loan.due_date)
		email = frappe.db.get_value("Library Member", loan.member, "email")
		if days < after or not email:
			continue
		frappe.sendmail(
			recipients=[email],
			subject=_("Overdue library book: {0}").format(loan.book_title),
			message=_(
				"<p>Dear {0},</p><p><strong>{1}</strong> (copy {2}) was due on {3} and is now"
				" {4} days overdue. Please return it to the library as soon as possible.</p><p>Library</p>"
			).format(loan.member_name, loan.book_title, loan.book_copy,
				frappe.utils.formatdate(loan.due_date), days),
			reference_doctype="Library Circulation",
			reference_name=loan.name,
		)
		sent += 1
	return sent


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
	expired = frappe.get_all(
		"Library Reservation",
		filters={"status": "Active", "expiry_date": ["<", today()]},
		fields=["name", "book"],
	)
	for reservation in expired:
		frappe.db.set_value("Library Reservation", reservation.name, "status", "Expired")
		reservations.notify_next(reservation.book)
	return len(expired)
