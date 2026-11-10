# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class LibraryReservation(Document):
	def validate(self):
		if self.status != "Active":
			return
		status = frappe.db.get_value("Library Member", self.member, "membership_status")
		if status != "Active":
			frappe.throw(_("Only active members can reserve books."))
		duplicate = frappe.db.exists("Library Reservation", {
			"member": self.member, "book": self.book, "status": "Active", "name": ["!=", self.name],
		})
		if duplicate:
			frappe.throw(_("This member already has an active reservation for this book: {0}.").format(duplicate))
		if self.is_new() and not self.priority:
			self.priority = frappe.db.count("Library Reservation", {"book": self.book, "status": "Active"}) + 1
