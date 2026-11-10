# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from library.library.utils import source_user


class LibraryMember(Document):
	def validate(self):
		if self.reference_doctype == "Student":
			if not self.student:
				frappe.throw(_("Select the Student this member belongs to."))
			self.employee = None
		elif self.reference_doctype == "Employee":
			if not self.employee:
				frappe.throw(_("Select the Employee this member belongs to."))
			self.student = None
		else:
			self.student = self.employee = None
		self.user = source_user(self)
		self.membership_status = self.membership_status or "Active"
		if (self.membership_start_date and self.membership_end_date
				and getdate(self.membership_end_date) < getdate(self.membership_start_date)):
			frappe.throw(_("The membership end date cannot be before its start date."))
