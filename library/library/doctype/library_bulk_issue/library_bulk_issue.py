# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from library.library import school


class LibraryBulkIssue(Document):
	def validate(self):
		if bool(self.student_group) == bool(self.student_batch):
			frappe.throw(_("Choose either a Student Group or a Class / Batch."))
		self.academic_year = self.academic_year or school.current_academic_year()
		if not self.items:
			frappe.throw(_("Add the books each student gets."))
		for row in self.items:
			book_type = frappe.db.get_value("Library Book", row.book, "book_type")
			if book_type != "Issue":
				frappe.throw(_("Row {0}: only Issue-type books can be issued.").format(row.idx))
			if flt(row.qty) <= 0:
				frappe.throw(_("Row {0}: the quantity must be more than zero.").format(row.idx))
		if not self.is_new() and self.status in ("Queued", "Running"):
			frappe.throw(_("This bulk issue is running; wait until it finishes."))

	def get_students(self):
		if self.student_group:
			students = school.students_in_group(self.student_group)
			return frappe.get_all("Student", filters={"name": ["in", students or [""]], "enabled": 1},
				pluck="name", order_by="name")
		return school.students_in_batch(self.student_batch, self.academic_year)

	@frappe.whitelist()
	def start(self):
		self.check_permission("write")
		if self.status not in ("Draft", "Completed with Errors"):
			frappe.throw(_("This bulk issue is {0}.").format(self.status))
		students = self.get_students()
		if not students:
			frappe.throw(_("No enabled students found in {0}.").format(self.student_group or self.student_batch))
		self.db_set({"status": "Queued", "total_students": len(students)})
		frappe.enqueue(
			"library.api.bulk.run_bulk_issue",
			queue="long",
			timeout=7200,
			job_id=f"library-bulk-issue-{self.name}",
			deduplicate=True,
			enqueue_after_commit=True,
			bulk_issue=self.name,
			user=frappe.session.user,
		)
		return len(students)
