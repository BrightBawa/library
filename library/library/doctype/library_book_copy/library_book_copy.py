# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import getseries

from library.library.stats import update_book_stats


class LibraryBookCopy(Document):
	def autoname(self):
		# <book>-0001, -0002, ... counted per book. A naming expression cannot do this:
		# ".{book}.-.####" has an empty series prefix, which Frappe refuses because another
		# DocType already uses it.
		if not self.book:
			frappe.throw(_("Select the book this copy belongs to."))
		self.name = f"{self.book}-{getseries(self.book + '-', 4)}"

	def on_update(self):
		update_book_stats(self.book)
		before = self.get_doc_before_save()
		if before and before.book != self.book:
			update_book_stats(before.book)

	def after_delete(self):
		update_book_stats(self.book)
