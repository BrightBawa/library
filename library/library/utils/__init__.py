# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt
"""Library Members from Students and Employees, and their status sync."""

import frappe
from frappe import _
from frappe.utils import cint

SOURCES = {
	"Student": {
		"link": "student",
		"name_field": "student_name",
		"filters": {"enabled": 1},
		"setting": "student_membership_type",
	},
	"Employee": {
		"link": "employee",
		"name_field": "employee_name",
		"filters": {"status": "Active"},
		"setting": "employee_membership_type",
	},
}


def source_user(member):
	if member.reference_doctype == "Student" and member.student:
		return frappe.db.get_value("Student", member.student, "user")
	if member.reference_doctype == "Employee" and member.employee:
		return frappe.db.get_value("Employee", member.employee, "user_id")
	return None


def _member_values(doctype, source):
	if doctype == "Student":
		return {
			"full_name": source.student_name,
			"email": source.get("student_email_id"),
			"phone": source.get("student_mobile_number"),
		}
	return {
		"full_name": source.employee_name,
		"email": source.get("company_email") or source.get("personal_email"),
		"phone": source.get("cell_number"),
	}


def get_default_membership_type():
	return frappe.db.get_value("Library Membership Type", {"is_active": 1}, "name") or "Standard"


def membership_type_for(doctype):
	return (frappe.db.get_single_value("Library Settings", SOURCES[doctype]["setting"])
		or get_default_membership_type())


def existing_member(doctype, name):
	return frappe.db.get_value("Library Member", {"reference_doctype": doctype, SOURCES[doctype]["link"]: name})


def create_member(doctype, source):
	"""Insert the Library Member for a Student or Employee and return its name."""
	member = frappe.get_doc({
		"doctype": "Library Member",
		"reference_doctype": doctype,
		SOURCES[doctype]["link"]: source.name,
		"member_id": source.name,
		"membership_type": membership_type_for(doctype),
		**_member_values(doctype, source),
	})
	member.insert(ignore_permissions=True)
	return member.name


def _auto_create(doctype, doc):
	setting = "auto_create_members_from_students" if doctype == "Student" else "auto_create_members_from_employees"
	if not cint(frappe.db.get_single_value("Library Settings", setting)) or existing_member(doctype, doc.name):
		return
	try:
		name = create_member(doctype, doc)
		frappe.msgprint(_("Library Member {0} created.").format(name), alert=True, indicator="green")
	except Exception:
		frappe.log_error(title=f"Library Member not created for {doctype} {doc.name}")


def auto_create_library_member_from_student(doc, method=None):
	_auto_create("Student", doc)


def auto_create_library_member_from_employee(doc, method=None):
	_auto_create("Employee", doc)


def _source_status(doc):
	if doc.doctype == "Student":
		return "Active" if cint(doc.enabled) else "Expired"
	return {"Active": "Active", "Suspended": "Suspended"}.get(doc.status, "Expired")


def sync_library_member_status(doc, method=None):
	"""on_update of Student / Employee: follow the source's status and user.

	Only a change of the source's own status moves the member, so a status a librarian
	set by hand (Suspended, Cancelled) stays until the Student or Employee changes. A
	member Cancelled by hand is never reactivated.
	"""
	link = SOURCES[doc.doctype]["link"]
	status_field = "enabled" if doc.doctype == "Student" else "status"
	before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
	source_changed = before is None or before.get(status_field) != doc.get(status_field)
	target = _source_status(doc)
	user = doc.get("user") if doc.doctype == "Student" else doc.get("user_id")

	for member in frappe.get_all("Library Member", filters={link: doc.name},
			fields=["name", "membership_status", "user"]):
		changes = {}
		if source_changed and target != member.membership_status:
			if not (target == "Active" and member.membership_status == "Cancelled"):
				changes["membership_status"] = target
		if (user or None) != (member.user or None):
			changes["user"] = user
		if changes:
			frappe.db.set_value("Library Member", member.name, changes)


def sync_members(sources=None, user=None, commit_every=100):
	"""Create a Library Member for every enabled Student / active Employee that has none.

	Runs as a background job (or from the console). Each source record is its own
	savepoint, so one failure is counted and skipped without undoing the rest.
	"""
	sources = frappe.parse_json(sources) if isinstance(sources, str) else (sources or list(SOURCES))
	result = {}
	failures = []
	for doctype in sources:
		spec = SOURCES[doctype]
		have = set(frappe.get_all("Library Member", filters={"reference_doctype": doctype}, pluck=spec["link"]))
		fields = ["name", spec["name_field"], *(
			("student_email_id", "student_mobile_number") if doctype == "Student"
			else ("company_email", "personal_email", "cell_number"))]
		created = skipped = failed = 0
		for i, source in enumerate(frappe.get_all(doctype, filters=spec["filters"], fields=fields, order_by="name")):
			if source.name in have:
				skipped += 1
				continue
			frappe.db.savepoint("library_member_sync")
			try:
				create_member(doctype, source)
				created += 1
			except Exception as e:
				frappe.db.rollback(save_point="library_member_sync")
				failed += 1
				failures.append(f"{doctype} {source.name}: {e}")
			if commit_every and (i + 1) % commit_every == 0:
				frappe.db.commit()
		result[doctype] = {"created": created, "skipped": skipped, "failed": failed}
	if failures:
		frappe.log_error(title="Library Member sync: some records failed", message="\n".join(failures[:200]))
	if user:
		lines = "<br>".join(
			_("{0}: {1} created, {2} already members, {3} failed").format(
				_(dt), r["created"], r["skipped"], r["failed"]) for dt, r in result.items())
		frappe.publish_realtime("msgprint", {"message": lines, "title": _("Library Member sync finished")},
			user=user)
	return result
