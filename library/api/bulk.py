"""Background jobs for the library's bulk tools."""

import frappe
from frappe import _
from frappe.utils import strip_html

from library.library import billing, utils

PROGRESS_EVENT = "library_bulk_progress"


def _add_result(parent, idx, values):
	frappe.get_doc({
		"doctype": "Library Bulk Issue Result", "parent": parent, "parenttype": "Library Bulk Issue",
		"parentfield": "results", "idx": idx, **values,
	}).db_insert()


def _already_issued(student, academic_year, books):
	if not books:
		return []
	return frappe.db.sql_list("""
		select distinct r.book_title from `tabLibrary Book Issuance` i
		join `tabLibrary Book Issuance Item` r on r.parent = i.name
		where i.docstatus = 1 and i.student = %s and i.academic_year = %s and r.book in %s
	""", (student, academic_year, books))


def issue_to_student(bulk, student, billable_books):
	"""(status, issuance, message) for one student."""
	member = utils.existing_member("Student", student)
	if not member:
		member = utils.create_member("Student", frappe.get_doc("Student", student))
	if bulk.skip_already_issued:
		already = _already_issued(student, bulk.academic_year, billable_books)
		if already:
			return "Skipped", None, _("Already issued this year: {0}").format(", ".join(already))
	if billable_books and not billing.student_customer(student):
		return "Failed", None, _("No Customer for the billed books")
	issuance = frappe.get_doc({
		"doctype": "Library Book Issuance",
		"member": member,
		"posting_date": bulk.posting_date,
		"academic_year": bulk.academic_year,
		"remarks": _("Bulk issue {0}").format(bulk.name),
		"items": [{"book": row.book, "qty": row.qty} for row in bulk.items],
	})
	issuance.insert()
	issuance.submit()
	return "Created", issuance.name, None


def run_bulk_issue(bulk_issue, user=None, commit_every=10):
	"""Create and submit one Library Book Issuance per student of a Library Bulk Issue."""
	if user:
		frappe.set_user(user)
	bulk = frappe.get_doc("Library Bulk Issue", bulk_issue)
	bulk.db_set("status", "Running")
	frappe.db.commit()

	done = {r.student for r in bulk.results if r.status == "Created"}
	billable = [r.book for r in bulk.items if frappe.db.get_value("Library Book", r.book, "is_billable")]
	students = bulk.get_students()
	counts = {"Created": len(done), "Skipped": 0, "Failed": 0}
	frappe.db.delete("Library Bulk Issue Result", {"parent": bulk.name, "status": ["!=", "Created"]})
	idx = len(done)
	for position, student in enumerate(students, start=1):
		if student in done:
			continue
		frappe.local.message_log = []
		frappe.db.savepoint("library_bulk_issue")
		try:
			status, issuance, message = issue_to_student(bulk, student, billable)
		except Exception as e:
			frappe.db.rollback(save_point="library_bulk_issue")
			status, issuance, message = "Failed", None, strip_html(str(e))[:500] or e.__class__.__name__
		counts[status] += 1
		idx += 1
		_add_result(bulk.name, idx, {"student": student, "student_name": frappe.db.get_value("Student", student, "student_name"),
			"status": status, "issuance": issuance, "message": message})
		if position % commit_every == 0 or position == len(students):
			bulk.db_set({"created_count": counts["Created"], "skipped_count": counts["Skipped"],
				"failed_count": counts["Failed"]}, update_modified=False)
			frappe.db.commit()
			frappe.publish_realtime(PROGRESS_EVENT, {"name": bulk.name, "done": position, "total": len(students)},
				doctype=bulk.doctype, docname=bulk.name)
	bulk.db_set({
		"created_count": counts["Created"], "skipped_count": counts["Skipped"], "failed_count": counts["Failed"],
		"status": "Completed with Errors" if counts["Failed"] else "Completed",
	})
	frappe.db.commit()
	frappe.publish_realtime(PROGRESS_EVENT, {"name": bulk.name, "done": len(students), "total": len(students), "finished": 1},
		doctype=bulk.doctype, docname=bulk.name)
	return counts
