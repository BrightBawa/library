# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from library.library import billing
from library.library.stats import set_fine_amounts, update_member_stats


class LibraryFine(Document):
	# An invoiced fine's invoice is cancelled when the fine is waived.
	ignore_linked_doctypes = ("Sales Invoice",)

	def validate(self):
		if flt(self.fine_amount) < 0 or flt(self.paid_amount) < 0:
			frappe.throw(_("Fine and paid amounts cannot be negative."))
		if flt(self.paid_amount) > flt(self.fine_amount):
			frappe.throw(_("The paid amount cannot be more than the fine."))
		before = self.get_doc_before_save()
		was_invoiced = bool(before and before.payment_status == "Invoiced")
		if was_invoiced:
			if self.payment_status not in ("Invoiced", "Waived"):
				frappe.throw(_("This fine is billed on Sales Invoice {0}; its payment is recorded there. "
					"It can only be waived, which cancels that invoice.").format(self.sales_invoice))
			for field in ("fine_amount", "paid_amount", "member", "fine_type"):
				if before.get(field) != self.get(field):
					frappe.throw(_("An invoiced fine cannot be changed; waive it instead."))
		if self.payment_status == "Invoiced" and not self.sales_invoice:
			frappe.throw(_("Use \"Bill to Student Account\" to invoice a fine."))
		if self.payment_status == "Waived":
			if not (self.waiver_reason or "").strip():
				frappe.throw(_("Enter the reason for waiving this fine."))
			self.waived_by = self.waived_by or frappe.session.user
			if was_invoiced:
				billing.assert_unpaid(self.sales_invoice)
				self.flags.cancel_invoice = self.sales_invoice
		else:
			self.waiver_reason = None
			self.waived_by = None
		set_fine_amounts(self)

	def on_update(self):
		if self.flags.cancel_invoice:
			billing.cancel_document("Sales Invoice", self.flags.cancel_invoice)
		update_member_stats(self.member)

	def after_delete(self):
		update_member_stats(self.member)
