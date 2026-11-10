"""The first library dashboard (8 number cards, 4 charts) is replaced by the "Library ..." cards
and charts. Delete the old records (only those of module Library) and every row that shows them."""

import frappe

OLD = {
	"Number Card": ["Total Books", "Available Books", "Issued Books", "Overdue Books", "Active Members",
		"Total Members", "Outstanding Fines", "Active Reservations"],
	"Dashboard Chart": ["Circulation Trend", "Category Distribution", "Member Activity", "Fine Collection"],
}
LINKS = {
	"Number Card": (("Number Card Link", "card"), ("Workspace Number Card", "number_card_name")),
	"Dashboard Chart": (("Dashboard Chart Link", "chart"), ("Workspace Chart", "chart_name")),
}


def execute():
	for doctype, names in OLD.items():
		for name in names:
			if frappe.db.get_value(doctype, name, "module") != "Library":
				continue
			for child, field in LINKS[doctype]:
				frappe.db.delete(child, {field: name})
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
