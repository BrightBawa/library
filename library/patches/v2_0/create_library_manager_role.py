"""The library DocTypes give permissions to Library Manager: create the role before they sync."""

import frappe


def execute():
	if not frappe.db.exists("Role", "Library Manager"):
		frappe.get_doc({"doctype": "Role", "role_name": "Library Manager", "desk_access": 1}).insert(ignore_permissions=True)
