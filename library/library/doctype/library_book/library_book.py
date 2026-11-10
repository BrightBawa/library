# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from library.library import stock
from library.library.stats import book_stats


class LibraryBook(Document):
	@property
	def warehouse_qty(self):
		return stock.warehouse_qty(self.item) if self.book_type == "Issue" and self.item else 0

	@warehouse_qty.setter
	def warehouse_qty(self, value):
		pass  # computed from the Bin; a value sent by the form is ignored

	def validate(self):
		if self.book_type == "Issue":
			if not self.item:
				self.item = stock.make_book_item(self)
			elif not frappe.db.get_value("Item", self.item, "is_stock_item"):
				frappe.throw(_("Item {0} is not a stock item, so it cannot be issued from the library warehouse.").format(self.item))
			if self.is_billable and not flt(self.rate):
				self.rate = stock.item_rate(self.item)
		else:
			self.is_billable = 0
		self.update(book_stats(self.name, self.book_type, self.item))
