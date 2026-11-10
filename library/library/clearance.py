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


def make_clearance(student, academic_year=None, submit=True, remarks=None, automatic=False):
	"""Create (and submit) a Library Clearance for a student; returns the document."""
	doc = frappe.get_doc({"doctype": "Library Clearance", "student": student, "academic_year": academic_year,
		"remarks": remarks, "automatic": 1 if automatic else 0}).insert(ignore_permissions=True)
	if submit:
		doc.flags.ignore_permissions = True
		doc.submit()
	return doc


def on_student_update(doc, method=None):
	"""Student on_update: when a student is disabled, queue their library clearance.

	Only a background job is queued here, after the save commits, so disabling many students
	at once (a class leaving, a data import) stays fast. One job per student, deduplicated.
	"""
	before = doc.get_doc_before_save()
	if not before or not before.get("enabled") or doc.get("enabled"):
		return
	if not student_members(doc.name):
		return
	frappe.enqueue("library.library.clearance.run_student_clearance", queue="long", timeout=600,
		job_id=f"library-clearance-{doc.name}", deduplicate=True, enqueue_after_commit=True, student=doc.name)


def run_student_clearance(student):
	"""Background job: record the clearance of a disabled student; queue the managers' digest if not cleared."""
	if frappe.db.get_value("Student", student, "enabled"):
		return None  # enabled again before the job ran
	doc = make_clearance(student, automatic=True,
		remarks=_("Checked automatically when the student was disabled."))
	if doc.status == "Not Cleared":
		frappe.enqueue("library.library.clearance.send_clearance_digest", queue="long", timeout=600,
			job_id="library-clearance-digest", deduplicate=True, enqueue_after_commit=True)
	return doc.name


def send_clearance_digest():
	"""Background job: one email to the Library Managers listing every automatic clearance that is
	not cleared and not yet reported, however many students were disabled together."""
	pending = frappe.get_all("Library Clearance",
		filters={"docstatus": 1, "automatic": 1, "status": "Not Cleared", "managers_notified": 0},
		fields=["name", "student", "student_name", "student_batch", "total_owed"], order_by="student_name")
	if not pending:
		return 0
	managers = frappe.get_all("Has Role", filters={"role": "Library Manager", "parenttype": "User"}, pluck="parent")
	emails = frappe.get_all("User", filters={"name": ["in", managers or [""]], "enabled": 1}, pluck="email")
	if emails:
		lines = "".join(
			"<tr><td>{0}</td><td>{1}</td><td>{2}</td><td style='text-align:right'>{3}</td><td>{4}</td></tr>".format(
				frappe.utils.escape_html(c.student_name or ""), c.student, c.student_batch or "",
				frappe.format_value(c.total_owed, {"fieldtype": "Currency"}),
				frappe.utils.get_link_to_form("Library Clearance", c.name)) for c in pending)
		frappe.sendmail(recipients=emails,
			subject=_("Library: {0} disabled student(s) not cleared").format(len(pending)),
			message=_("<p>These students were disabled but still have items outstanding with the library:</p>")
				+ "<table border='1' cellpadding='4' style='border-collapse:collapse'><tr><th>{0}</th><th>{1}</th>"
				"<th>{2}</th><th>{3}</th><th>{4}</th></tr>{5}</table>".format(
					_("Student"), _("ID"), _("Class"), _("Owed"), _("Clearance"), lines))
	for c in pending:
		frappe.db.set_value("Library Clearance", c.name, "managers_notified", 1, update_modified=False)
	return len(pending)
