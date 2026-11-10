"""Library Members from Students and Employees: auto-create, bulk sync, status sync, patch.

Students and Employees are read from the live site and changed only in memory; the
sync functions are called directly, so no Student or Employee is ever saved.
"""

import copy
from unittest.mock import patch

import frappe

from library.library import utils
from library.patches.v2_0 import fill_member_status_and_user
from library.tests.utils import LibraryTestCase, make_member, set_settings


def _source(doctype, filters=None):
	name = frappe.db.get_value(doctype, filters or {}, "name")
	if not name:
		raise AssertionError(f"no {doctype} on this site to test with")
	return frappe.get_doc(doctype, name)


def _changed(doc, **values):
	"""The doc as on_update sees it: the new values, and the old ones as doc-before-save."""
	doc._doc_before_save = copy.deepcopy(doc)
	doc.update(values)
	return doc


def _member_for(doctype, source, **values):
	frappe.db.delete("Library Member", {utils.SOURCES[doctype]["link"]: source.name})
	link = utils.SOURCES[doctype]["link"]
	return make_member(f"_Test {doctype} Member", reference_doctype=doctype, **{link: source.name}, **values)


class TestMemberStatusSync(LibraryTestCase):
	def test_employee_status_drives_the_member(self):
		employee = _source("Employee", {"status": "Active"})
		member = _member_for("Employee", employee)
		self.assertEqual(member.user, employee.user_id)

		utils.sync_library_member_status(_changed(employee, status="Left"))
		self.assertEqual(frappe.db.get_value("Library Member", member.name, "membership_status"), "Expired")
		utils.sync_library_member_status(_changed(employee, status="Suspended"))
		self.assertEqual(frappe.db.get_value("Library Member", member.name, "membership_status"), "Suspended")
		utils.sync_library_member_status(_changed(employee, status="Active"))
		self.assertEqual(frappe.db.get_value("Library Member", member.name, "membership_status"), "Active")

	def test_a_hand_set_status_survives_unrelated_saves_and_cancelled_is_never_reactivated(self):
		employee = _source("Employee", {"status": "Active"})
		member = _member_for("Employee", employee, membership_status="Suspended")
		utils.sync_library_member_status(_changed(employee, cell_number="000"))  # status unchanged
		self.assertEqual(frappe.db.get_value("Library Member", member.name, "membership_status"), "Suspended")

		frappe.db.set_value("Library Member", member.name, "membership_status", "Cancelled")
		employee.status = "Left"
		utils.sync_library_member_status(_changed(employee, status="Active"))
		self.assertEqual(frappe.db.get_value("Library Member", member.name, "membership_status"), "Cancelled")

	def test_student_enabled_flag_and_user_follow(self):
		student = _source("Student", {"enabled": 1})
		member = _member_for("Student", student)
		utils.sync_library_member_status(_changed(student, enabled=0, user="Administrator"))
		values = frappe.db.get_value("Library Member", member.name, ["membership_status", "user"], as_dict=True)
		self.assertEqual((values.membership_status, values.user), ("Expired", "Administrator"))


class TestMemberCreation(LibraryTestCase):
	def test_auto_create_on_new_student_only_when_switched_on(self):
		student = _source("Student", {"enabled": 1})
		frappe.db.delete("Library Member", {"student": student.name})
		set_settings(auto_create_members_from_students=0, student_membership_type=self.mtype)
		utils.auto_create_library_member_from_student(student)
		self.assertFalse(utils.existing_member("Student", student.name))

		set_settings(auto_create_members_from_students=1)
		utils.auto_create_library_member_from_student(student)
		name = utils.existing_member("Student", student.name)
		member = frappe.get_doc("Library Member", name)
		self.assertEqual((member.full_name, member.membership_type, member.member_id, member.membership_status),
			(student.student_name, self.mtype, student.name, "Active"))
		utils.auto_create_library_member_from_student(student)  # no duplicate
		self.assertEqual(frappe.db.count("Library Member", {"student": student.name}), 1)

	def test_bulk_sync_creates_only_missing_members(self):
		names = frappe.get_all("Student", filters={"enabled": 1}, pluck="name", limit=3, order_by="name")
		frappe.db.delete("Library Member", {"student": ["in", names]})
		_member_for("Student", frappe.get_doc("Student", names[0]))
		set_settings(student_membership_type=self.mtype)
		only_these = dict(utils.SOURCES["Student"], filters={"enabled": 1, "name": ["in", names]})
		with patch.dict(utils.SOURCES, {"Student": only_these}):
			result = utils.sync_members(["Student"], commit_every=0)
		self.assertEqual(result, {"Student": {"created": 2, "skipped": 1, "failed": 0}})
		for name in names:
			self.assertEqual(frappe.db.count("Library Member", {"student": name}), 1)


class TestMemberPatch(LibraryTestCase):
	def test_empty_status_gets_the_source_status(self):
		employee = _source("Employee", {"status": "Active"})
		member = _member_for("Employee", employee)
		other = make_member("_Test No Source")
		frappe.db.set_value("Library Member", {"name": ["in", [member.name, other.name]]},
			{"membership_status": None, "user": None})
		fill_member_status_and_user.execute()
		values = frappe.db.get_value("Library Member", member.name, ["membership_status", "user"], as_dict=True)
		self.assertEqual((values.membership_status, values.user), ("Active", employee.user_id))
		self.assertEqual(frappe.db.get_value("Library Member", other.name, "membership_status"), "Active")
