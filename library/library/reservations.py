"""Reservation queue helpers shared by circulation and the daily job."""

import frappe
from frappe import _
from frappe.utils import add_days, today


def other_members_waiting(book, member):
	return frappe.db.exists(
		"Library Reservation", {"book": book, "status": "Active", "member": ["!=", member]}
	)


def fulfil(member, book, circulation):
	"""Mark the member's active reservation for the book fulfilled by this Issue."""
	name = frappe.db.get_value(
		"Library Reservation", {"book": book, "member": member, "status": "Active"}, order_by="creation"
	)
	if name:
		frappe.db.set_value("Library Reservation", name, {
			"status": "Fulfilled", "fulfilled_date": today(), "circulation": circulation,
		})


def notify_next(book):
	"""Tell the first member in the queue for this book that a copy is available."""
	first = frappe.get_all(
		"Library Reservation",
		filters={"book": book, "status": "Active", "notified_date": ["is", "not set"]},
		fields=["name", "member"],
		order_by="priority asc, reservation_date asc, creation asc",
		limit=1,
	)
	if not first:
		return None
	reservation = frappe.get_doc("Library Reservation", first[0].name)
	days = frappe.db.get_single_value("Library Settings", "reservation_expiry_days") or 3
	reservation.notified_date = today()
	reservation.expiry_date = add_days(today(), days)
	reservation.save(ignore_permissions=True)

	email = frappe.db.get_value("Library Member", reservation.member, "email")
	if email:
		member_name, title = (
			frappe.db.get_value("Library Member", reservation.member, "full_name"),
			frappe.db.get_value("Library Book", book, "book_title"),
		)
		frappe.sendmail(
			recipients=[email],
			subject=_("Reserved book available: {0}").format(title),
			message=_(
				"<p>Dear {0},</p><p>The book you reserved, <strong>{1}</strong>, is now available."
				" Please collect it from the library by <strong>{2}</strong>; after that the"
				" reservation expires.</p><p>Library</p>"
			).format(member_name, title, frappe.utils.formatdate(reservation.expiry_date)),
			reference_doctype="Library Reservation",
			reference_name=reservation.name,
		)
	return reservation.name
