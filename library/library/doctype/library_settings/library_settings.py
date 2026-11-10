# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class LibrarySettings(Document):
	def validate(self):
		if self.auto_create_members_from_students and not self.student_membership_type:
			frappe.throw(_("Select the membership type for students."))
		if self.auto_create_members_from_employees and not self.employee_membership_type:
			frappe.throw(_("Select the membership type for employees."))


@frappe.whitelist()
def sync_students_and_employees(sources=None):
	"""Queue the creation of Library Members for Students and/or Employees without one."""
	frappe.has_permission("Library Settings", "write", throw=True)
	sources = frappe.parse_json(sources) if sources else ["Student", "Employee"]
	if not set(sources) <= {"Student", "Employee"}:
		frappe.throw(_("Members can only be synced from Students and Employees."))
	frappe.enqueue(
		"library.library.utils.sync_members",
		queue="long",
		timeout=3600,
		job_id=f"library-member-sync-{'-'.join(sorted(sources))}",
		deduplicate=True,
		enqueue_after_commit=True,
		sources=sources,
		user=frappe.session.user,
	)
	return {"queued": sources}
