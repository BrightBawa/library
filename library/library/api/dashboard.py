# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import today, getdate


@frappe.whitelist()
def get_overdue_books_count():
	"""Get count of overdue books"""
	overdue_count = frappe.db.count("Library Circulation", {
		"docstatus": 1,
		"return_date": ["is", "not set"],
		"due_date": ["<", today()]
	})
	return overdue_count
