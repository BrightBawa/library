"""Library clearance of a student: unreturned loans, unpaid fines, active reservations (and, for a
teacher's own member record, class sets still out). Used by Library Clearance and its bulk tool."""

import frappe
from frappe import _
from frappe.utils import flt, formatdate

from library.library.stats import OPEN_LOAN


def outstanding(members):
	"""Rows of what the members still owe the library."""
	if not members:
		return []
	rows = []
	for loan in frappe.get_all("Library Circulation", filters=dict(OPEN_LOAN, member=["in", members]),
			fields=["name", "book_title", "book_copy", "due_date"]):
		rows.append({"check_type": "Unreturned Loan", "reference_doctype": "Library Circulation", "reference_name": loan.name,
			"detail": _("{0} ({1}), due {2}").format(loan.book_title, loan.book_copy, formatdate(loan.due_date)), "amount": 0})
	for fine in frappe.get_all("Library Fine", filters={"member": ["in", members],
			"payment_status": ["in", ["Unpaid", "Partially Paid", "Invoiced"]]},
			fields=["name", "fine_type", "outstanding_amount", "payment_status", "sales_invoice"]):
		owed = flt(fine.outstanding_amount)
		if fine.payment_status == "Invoiced":
			owed = flt(frappe.db.get_value("Sales Invoice", fine.sales_invoice, "outstanding_amount")) if fine.sales_invoice else 0
			if owed <= 0:
				continue
		rows.append({"check_type": "Unpaid Fine", "reference_doctype": "Library Fine", "reference_name": fine.name,
			"detail": _("{0} fine").format(_(fine.fine_type)) + (
				_(", owed on invoice {0}").format(fine.sales_invoice) if fine.payment_status == "Invoiced" else ""),
			"amount": owed})
	for reservation in frappe.get_all("Library Reservation", filters={"member": ["in", members], "status": "Active"},
			fields=["name", "book"]):
		rows.append({"check_type": "Active Reservation", "reference_doctype": "Library Reservation",
			"reference_name": reservation.name, "detail": frappe.db.get_value("Library Book", reservation.book, "book_title"),
			"amount": 0})
	for loan in frappe.get_all("Library Class Set Loan", filters={"teacher": ["in", members], "docstatus": 1,
			"status": ["in", ["Open", "Partly Returned", "Overdue"]]}, fields=["name", "due_date"]):
		rows.append({"check_type": "Class Set Loan", "reference_doctype": "Library Class Set Loan", "reference_name": loan.name,
			"detail": _("Due {0}").format(formatdate(loan.due_date)), "amount": 0})
	return rows


def student_members(student):
	return frappe.get_all("Library Member", filters={"student": student}, pluck="name")


def make_clearance(student, academic_year=None, submit=True, remarks=None):
	"""Create (and submit) a Library Clearance for a student; returns the document."""
	doc = frappe.get_doc({"doctype": "Library Clearance", "student": student, "academic_year": academic_year,
		"remarks": remarks}).insert(ignore_permissions=True)
	if submit:
		doc.flags.ignore_permissions = True
		doc.submit()
	return doc


def on_student_update(doc, method=None):
	"""Student on_update: when a student is disabled, record their library clearance and tell the
	Library Managers if they are not cleared."""
	before = doc.get_doc_before_save()
	if not before or not before.get("enabled") or doc.get("enabled"):
		return
	if not student_members(doc.name):
		return
	clearance = make_clearance(doc.name, remarks=_("Checked automatically when the student was disabled."))
	if clearance.status == "Not Cleared":
		managers = frappe.get_all("Has Role", filters={"role": "Library Manager", "parenttype": "User"}, pluck="parent")
		emails = frappe.get_all("User", filters={"name": ["in", managers or [""]], "enabled": 1}, pluck="email")
		if emails:
			frappe.sendmail(recipients=emails, subject=_("Not cleared by the library: {0}").format(doc.student_name),
				message=_("<p>{0} ({1}) was disabled but still has {2} outstanding item(s) with the library, "
					"{3} owed. See {4}.</p>").format(doc.student_name, doc.name, len(clearance.items),
					frappe.format_value(clearance.total_owed, {"fieldtype": "Currency"}),
					frappe.utils.get_link_to_form("Library Clearance", clearance.name)),
				reference_doctype="Library Clearance", reference_name=clearance.name)
