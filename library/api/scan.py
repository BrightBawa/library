"""Barcode and ISBN scanning for library forms."""

import frappe


@frappe.whitelist()
def resolve(code):
	"""The Library Book (and copy, if a copy barcode was scanned) for a scanned code.

	Tried in order: Library Book ISBN, Library Book Copy barcode or name, Item Barcode
	of a book's item.
	"""
	frappe.has_permission("Library Book", "read", throw=True)
	code = (code or "").strip()
	if not code:
		return None
	book = frappe.db.get_value("Library Book", {"isbn": code})
	copy = None
	if not book:
		copy = frappe.db.get_value("Library Book Copy", {"barcode": code}) or (
			code if frappe.db.exists("Library Book Copy", code) else None)
		book = frappe.db.get_value("Library Book Copy", copy, "book") if copy else None
	if not book:
		item = frappe.db.get_value("Item Barcode", {"barcode": code}, "parent")
		book = frappe.db.get_value("Library Book", {"item": item}) if item else None
	if not book:
		return None
	values = frappe.db.get_value("Library Book", book, ["name", "book_title", "book_type", "is_billable"], as_dict=True)
	values.copy = copy
	return values
