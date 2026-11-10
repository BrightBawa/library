# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt
"""Stocktake of the library: Issue-type books in the library warehouse and lending copies on the shelf.
Submitting posts a Stock Reconciliation for the variances and marks copies not found as Lost."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from library.library import billing
from library.library.doctype.library_issuance_return.library_issuance_return import require_library_manager
from library.library.stats import update_book_stats
from library.library.stock import get_settings, refresh_books_for_items, require, warehouse_qty

SHELF_STATUSES = ("Available", "Reserved", "Maintenance", "Damaged")


class LibraryStockCount(Document):
	ignore_linked_doctypes = ("Stock Reconciliation",)

	def validate(self):
		settings = get_settings()
		require(settings, "company", "library_warehouse")
		self.company = settings.company
		self.warehouse = self.warehouse or settings.library_warehouse
		for row in self.items:
			row.variance = flt(row.counted_qty) - flt(row.system_qty)
		self.total_variance = sum(flt(r.variance) for r in self.items)
		self.copies_not_found = sum(1 for c in self.copies if not c.found)

	@frappe.whitelist()
	def load_books(self):
		"""Fill the count with today's system quantities and the copies that should be on the shelf."""
		self.check_permission("write")
		if self.docstatus != 0:
			frappe.throw(_("Only a draft count can be loaded."))
		self.validate()
		self.set("items", [])
		for book in frappe.get_all("Library Book", filters={"book_type": "Issue", "item": ["is", "set"]},
				fields=["name", "book_title", "item"], order_by="book_title"):
			qty = warehouse_qty(book.item, self.warehouse)
			rate = frappe.db.get_value("Bin", {"item_code": book.item, "warehouse": self.warehouse}, "valuation_rate")
			self.append("items", {"book": book.name, "book_title": book.book_title, "item": book.item,
				"system_qty": qty, "counted_qty": qty, "valuation_rate": flt(rate)})
		self.set("copies", [])
		for copy in frappe.get_all("Library Book Copy", filters={"status": ["in", SHELF_STATUSES]},
				fields=["name", "book", "book_title", "status"], order_by="book_title, name"):
			self.append("copies", {"copy": copy.name, "book": copy.book, "book_title": copy.book_title,
				"previous_status": copy.status, "found": 0})
		self.save()
		return {"books": len(self.items), "copies": len(self.copies)}

	def before_submit(self):
		require_library_manager(_("post a stock count"))

	def on_submit(self):
		changed = [r for r in self.items if flt(r.variance)]
		if changed:
			reconciliation = billing.make_stock_reconciliation(company=self.company, posting_date=self.posting_date,
				document=self, rows=[{"item_code": r.item, "qty": r.counted_qty,
					"valuation_rate": r.valuation_rate or item_rate(r.item)} for r in changed])
			self.db_set("stock_reconciliation", reconciliation.name)
		for copy in self.copies:
			if not copy.found:
				frappe.db.set_value("Library Book Copy", copy.copy, "status", "Lost")
		self.refresh_counters()

	def before_cancel(self):
		require_library_manager(_("cancel a stock count"))

	def on_cancel(self):
		billing.cancel_document("Stock Reconciliation", self.stock_reconciliation)
		for copy in self.copies:
			if not copy.found and frappe.db.get_value("Library Book Copy", copy.copy, "status") == "Lost":
				frappe.db.set_value("Library Book Copy", copy.copy, "status", copy.previous_status)
		self.refresh_counters()

	def refresh_counters(self):
		refresh_books_for_items({r.item for r in self.items})
		for book in {c.book for c in self.copies if not c.found}:
			update_book_stats(book)


def item_rate(item):
	"""A rate for books counted where the warehouse has none yet."""
	return flt(frappe.db.get_value("Item", item, "valuation_rate"))


@frappe.whitelist()
def scan_copy(name, code):
	"""Tick the scanned copy as found on a draft count; returns the copy or None."""
	doc = frappe.get_doc("Library Stock Count", name)
	doc.check_permission("write")
	copy = frappe.db.get_value("Library Book Copy", {"barcode": code}) or (code if frappe.db.exists("Library Book Copy", code) else None)
	for row in doc.copies:
		if row.copy == copy:
			row.found = 1
			doc.save()
			return copy
	return None
