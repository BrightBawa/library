# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from library.library.stats import update_book_stats


class LibraryBookCopy(Document):
	def on_update(self):
		update_book_stats(self.book)
		before = self.get_doc_before_save()
		if before and before.book != self.book:
			update_book_stats(before.book)

	def after_delete(self):
		update_book_stats(self.book)
