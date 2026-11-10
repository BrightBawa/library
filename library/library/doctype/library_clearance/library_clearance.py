# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from library.library import clearance, school


class LibraryClearance(Document):
	def validate(self):
		"""Checked on every save and again on submit, so a submitted clearance is the state at submission."""
		members = clearance.student_members(self.student)
		self.member = members[0] if members else None
		self.student_name = frappe.db.get_value("Student", self.student, "student_name")
		self.academic_year = self.academic_year or school.current_academic_year()
		self.student_batch = school.student_batch(self.student, self.academic_year)
		self.set("items", clearance.outstanding(members))
		self.status = "Not Cleared" if self.items else "Cleared"
		self.total_owed = sum(flt(r.amount) for r in self.items)
