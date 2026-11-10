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
		self.validate_company_records()

	def validate_company_records(self):
		"""Warehouses, accounts and cost center must be leaves of the selected company."""
		checks = [
			("library_warehouse", "Warehouse", None),
			("stores_warehouse", "Warehouse", None),
			("default_cost_center", "Cost Center", None),
			("default_income_account", "Account", "Income"),
			("issue_expense_account", "Account", "Expense"),
		]
		for fieldname, doctype, root_type in checks:
			value = self.get(fieldname)
			if not value:
				continue
			label = _(self.meta.get_label(fieldname))
			fields = ["company", "is_group"] + (["root_type"] if root_type else [])
			record = frappe.db.get_value(doctype, value, fields, as_dict=True)
			if not record:
				continue  # link validation reports a missing record
			if not self.company:
				frappe.throw(_("Select the Company before setting {0}.").format(label))
			if record.company != self.company:
				frappe.throw(_("{0} {1} belongs to {2}, not {3}.").format(label, value, record.company, self.company))
			if record.is_group:
				frappe.throw(_("{0} {1} is a group; select one below it.").format(label, value))
			if root_type and record.root_type != root_type:
				frappe.throw(_("{0} must be an {1} account.").format(label, root_type))
		if self.library_warehouse and self.library_warehouse == self.stores_warehouse:
			frappe.throw(_("The library and stores warehouses must be different."))


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
