"""Library fines: the rate, the one Overdue fine per loan, and Damage/Lost fines."""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today


def fines_enabled():
	return bool(frappe.db.get_single_value("Library Settings", "enable_fines"))


def fine_per_day(member):
	membership_type = frappe.db.get_value("Library Member", member, "membership_type")
	rate = flt(frappe.db.get_value("Library Membership Type", membership_type, "fine_per_day"))
	return rate or flt(frappe.db.get_single_value("Library Settings", "default_fine_per_day"))


def days_overdue(due_date, as_of=None):
	if not due_date:
		return 0
	return max(date_diff(getdate(as_of or today()), getdate(due_date)), 0)


def sync_overdue_fine(issue, as_of=None):
	"""Keep the one Overdue fine of an Issue equal to days overdue x the member's rate.

	The fine links to the Issue. The daily job calls this for open loans and the Return
	calls it once more with the return date, which makes the amount final. An unpaid
	fine that drops to zero (a back-dated return) is removed.
	"""
	days = days_overdue(issue.due_date, as_of)
	amount = days * fine_per_day(issue.member) if fines_enabled() else 0
	name = frappe.db.get_value("Library Fine", {"circulation": issue.name, "fine_type": "Overdue"})
	if name:
		fine = frappe.get_doc("Library Fine", name)
		if fine.payment_status in ("Paid", "Waived") or flt(fine.paid_amount):
			return fine  # settled: never change what was paid or waived
		if not amount:
			frappe.delete_doc("Library Fine", name, ignore_permissions=True, force=True)
			return None
		if flt(fine.fine_amount) != amount:
			fine.fine_amount = amount
			fine.save(ignore_permissions=True)
		return fine
	if amount:
		return create_fine(issue.member, "Overdue", amount, issue.name,
			_("{0} days overdue").format(days))
	return None


def create_fine(member, fine_type, amount, circulation, notes=None):
	fine = frappe.get_doc({
		"doctype": "Library Fine",
		"member": member,
		"fine_type": fine_type,
		"fine_date": today(),
		"fine_amount": flt(amount),
		"circulation": circulation,
		"notes": notes,
	})
	fine.insert(ignore_permissions=True)
	return fine


def condition_fine(return_doc):
	"""Damage or Lost fine for a Return, linked to the Return itself."""
	if not fines_enabled() or return_doc.condition_on_return not in ("Damaged", "Lost"):
		return None
	setting = lambda field: frappe.db.get_single_value("Library Settings", field)  # noqa: E731
	if return_doc.condition_on_return == "Damaged":
		amount = flt(setting("damage_fine_amount"))
		return create_fine(return_doc.member, "Damage", amount, return_doc.name) if amount else None
	cost = flt(frappe.db.get_value("Library Book Copy", return_doc.book_copy, "cost"))
	amount = cost * flt(setting("lost_book_fine_multiplier") or 1)
	if not amount:
		frappe.msgprint(
			_("No Lost fine was created: copy {0} has no cost.").format(return_doc.book_copy),
			indicator="orange",
		)
		return None
	return create_fine(return_doc.member, "Lost", amount, return_doc.name)


def remove_unsettled_fines(circulation):
	"""Delete the fines a cancelled document created, refusing if any was paid or waived."""
	for fine in frappe.get_all("Library Fine", filters={"circulation": circulation},
			fields=["name", "payment_status", "paid_amount"]):
		if fine.payment_status in ("Paid", "Partially Paid", "Waived") or flt(fine.paid_amount):
			frappe.throw(_("Fine {0} is already {1}. Settle it before cancelling {2}.").format(
				fine.name, fine.payment_status.lower(), circulation))
		frappe.delete_doc("Library Fine", fine.name, ignore_permissions=True, force=True)
