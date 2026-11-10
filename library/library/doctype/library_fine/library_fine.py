# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from library.library.stats import set_fine_amounts, update_member_stats


class LibraryFine(Document):
	def validate(self):
		if flt(self.fine_amount) < 0 or flt(self.paid_amount) < 0:
			frappe.throw(_("Fine and paid amounts cannot be negative."))
		if flt(self.paid_amount) > flt(self.fine_amount):
			frappe.throw(_("The paid amount cannot be more than the fine."))
		if self.payment_status == "Waived":
			if not (self.waiver_reason or "").strip():
				frappe.throw(_("Enter the reason for waiving this fine."))
			self.waived_by = self.waived_by or frappe.session.user
		else:
			self.waiver_reason = None
			self.waived_by = None
		set_fine_amounts(self)

	def on_update(self):
		update_member_stats(self.member)

	def after_delete(self):
		update_member_stats(self.member)
