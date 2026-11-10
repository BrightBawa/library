"""Members created before the status default existed have no membership_status (99 on
portal.gcihs.edu.gh on 2026-11-10, all for active employees). Give them their source's
status and fill the new `user` field for every member."""

import frappe

from library.library.utils import _source_status, source_user


def execute():
	for member in frappe.get_all("Library Member",
			fields=["name", "reference_doctype", "student", "employee", "membership_status", "user"]):
		changes = {}
		source = None
		if member.reference_doctype == "Student" and member.student:
			source = frappe.db.get_value("Student", member.student, ["name", "enabled"], as_dict=True)
			if source:
				source.doctype = "Student"
		elif member.reference_doctype == "Employee" and member.employee:
			source = frappe.db.get_value("Employee", member.employee, ["name", "status"], as_dict=True)
			if source:
				source.doctype = "Employee"
		if not member.membership_status:
			changes["membership_status"] = _source_status(source) if source else "Active"
		user = source_user(member)
		if (user or None) != (member.user or None):
			changes["user"] = user
		if changes:
			frappe.db.set_value("Library Member", member.name, changes, update_modified=False)
