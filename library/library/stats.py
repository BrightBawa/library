"""Derived counters on Library Book, Library Member and Library Fine.

The counters are read-only fields that the library code keeps in step with the
records they summarise. Every function recomputes from the source rows, so calling
one twice, or after a cancel, always gives the right figure.
"""

import frappe
from frappe.utils import flt, today

OPEN_LOAN = {"docstatus": 1, "transaction_type": "Issue", "return_date": ["is", "not set"]}


def book_stats(book, book_type="Lending", item=None):
	"""total_copies, available_copies and book_status of a book.

	Lending: from its copies (every copy not Lost counts in the total). Issue: the
	quantity in the library warehouse.
	"""
	if book_type == "Issue":
		from library.library.stock import warehouse_qty

		qty = int(warehouse_qty(item))
		return {"total_copies": qty, "available_copies": qty,
			"book_status": "Available" if qty > 0 else "Out of Stock"}
	by_status = dict(
		frappe.db.sql(
			"select status, count(*) from `tabLibrary Book Copy` where book = %s group by status",
			book,
		)
	) if book else {}
	total = sum(count for status, count in by_status.items() if status != "Lost")
	available = by_status.get("Available", 0)
	if not total:
		book_status = "Out of Stock"
	elif available:
		book_status = "Available"
	else:
		book_status = "All Issued"
	return {"total_copies": total, "available_copies": available, "book_status": book_status}


def update_book_stats(book):
	if not book:
		return
	values = frappe.db.get_value("Library Book", book, ["book_type", "item"], as_dict=True)
	if not values:
		return
	frappe.db.set_value("Library Book", book, book_stats(book, values.book_type, values.item),
		update_modified=False)


def update_member_stats(member):
	"""books_issued, total_books_borrowed, overdue_books and outstanding_balance."""
	if not member or not frappe.db.exists("Library Member", member):
		return
	open_filters = dict(OPEN_LOAN, member=member)
	outstanding = frappe.db.sql(
		"""select coalesce(sum(outstanding_amount), 0) from `tabLibrary Fine`
		where member = %s and payment_status in ('Unpaid', 'Partially Paid')""",
		member,
	)[0][0]
	frappe.db.set_value(
		"Library Member",
		member,
		{
			"books_issued": frappe.db.count("Library Circulation", open_filters),
			"total_books_borrowed": frappe.db.count(
				"Library Circulation", {"member": member, "docstatus": 1, "transaction_type": "Issue"}
			),
			"overdue_books": frappe.db.count(
				"Library Circulation", dict(open_filters, due_date=["<", today()])
			),
			"outstanding_balance": flt(outstanding),
		},
		update_modified=False,
	)


def members_with_open_loans():
	return frappe.get_all("Library Circulation", filters=OPEN_LOAN, pluck="member", distinct=True)


def set_fine_amounts(fine):
	"""Derive outstanding_amount and payment_status on a Library Fine being saved."""
	fine.fine_amount = flt(fine.fine_amount)
	fine.paid_amount = flt(fine.paid_amount)
	if fine.payment_status == "Waived":
		fine.outstanding_amount = 0
		return
	fine.outstanding_amount = max(fine.fine_amount - fine.paid_amount, 0)
	if fine.fine_amount and fine.paid_amount >= fine.fine_amount:
		fine.payment_status = "Paid"
	elif fine.paid_amount > 0:
		fine.payment_status = "Partially Paid"
	else:
		fine.payment_status = "Unpaid"
