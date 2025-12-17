# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today, date_diff, add_days


class LibraryCirculation(Document):
	def validate(self):
		self.validate_member()
		self.validate_book_copy()
		self.set_defaults()
		self.calculate_overdue()
	
	def before_submit(self):
		if self.transaction_type == "Issue":
			self.validate_issue()
		elif self.transaction_type == "Return":
			self.validate_return()
		elif self.transaction_type == "Renew":
			self.validate_renewal()
	
	def on_submit(self):
		if self.transaction_type == "Issue":
			self.issue_book()
		elif self.transaction_type == "Return":
			self.return_book()
		elif self.transaction_type == "Renew":
			self.renew_book()
	
	def on_cancel(self):
		self.revert_transaction()
	
	def validate_member(self):
		"""Validate that member exists and has active membership"""
		if not self.member:
			frappe.throw(_("Please select a Library Member"))
		
		# Check if member has active membership
		active_membership = frappe.db.exists(
			"Library Membership",
			{
				"member": self.member,
				"docstatus": 1,
				"from_date": ["<=", today()],
				"to_date": [">=", today()]
			}
		)
		
		if not active_membership:
			frappe.throw(_("Member {0} does not have an active membership").format(
				frappe.bold(self.member_name or self.member)
			))
	
	def validate_book_copy(self):
		"""Validate that book copy exists and is available"""
		if not self.book_copy:
			frappe.throw(_("Please select a Book Copy"))
		
		book_copy = frappe.get_doc("Library Book Copy", self.book_copy)
		
		if self.transaction_type == "Issue":
			if book_copy.status != "Available":
				frappe.throw(_("Book Copy {0} is not available for issue").format(
					frappe.bold(self.book_copy)
				))
	
	def set_defaults(self):
		"""Set default values for fields"""
		if not self.transaction_date:
			self.transaction_date = today()
		
		# Set member name
		if self.member and not self.member_name:
			self.member_name = frappe.db.get_value("Library Member", self.member, "member_name")
		
		# Set book title
		if self.book_copy and not self.book_title:
			book = frappe.db.get_value("Library Book Copy", self.book_copy, "book")
			if book:
				self.book_title = frappe.db.get_value("Library Book", book, "book_title")
		
		# Set due date for issue transactions
		if self.transaction_type == "Issue" and not self.due_date:
			# Get loan period from membership type
			membership = frappe.db.get_value(
				"Library Membership",
				{
					"member": self.member,
					"docstatus": 1,
					"from_date": ["<=", today()],
					"to_date": [">=", today()]
				},
				"membership_type"
			)
			
			if membership:
				loan_period = frappe.db.get_value("Library Membership Type", membership, "loan_period") or 14
			else:
				loan_period = frappe.db.get_single_value("Library Settings", "default_loan_period") or 14
			
			self.due_date = add_days(self.transaction_date, loan_period)
	
	def calculate_overdue(self):
		"""Calculate overdue days and fine"""
		if self.transaction_type == "Return" and self.return_date:
			if self.due_date and getdate(self.return_date) > getdate(self.due_date):
				self.overdue_days = date_diff(self.return_date, self.due_date)
				
				# Get fine per day from settings
				fine_per_day = frappe.db.get_single_value("Library Settings", "fine_per_day") or 1.0
				self.fine_amount = self.overdue_days * fine_per_day
			else:
				self.overdue_days = 0
				self.fine_amount = 0.0
	
	def validate_issue(self):
		"""Validate issue transaction"""
		# Check if member has reached maximum books limit
		membership = frappe.db.get_value(
			"Library Membership",
			{
				"member": self.member,
				"docstatus": 1,
				"from_date": ["<=", today()],
				"to_date": [">=", today()]
			},
			"membership_type"
		)
		
		if membership:
			max_books = frappe.db.get_value("Library Membership Type", membership, "max_books") or 3
		else:
			max_books = frappe.db.get_single_value("Library Settings", "default_max_books") or 3
		
		# Count current issued books
		issued_books = frappe.db.count(
			"Library Circulation",
			{
				"member": self.member,
				"docstatus": 1,
				"transaction_type": "Issue",
				"return_date": ["is", "not set"]
			}
		)
		
		if issued_books >= max_books:
			frappe.throw(_("Member {0} has reached the maximum limit of {1} books").format(
				frappe.bold(self.member_name or self.member),
				frappe.bold(max_books)
			))
		
		# Check if this book is already issued to this member
		existing_issue = frappe.db.exists(
			"Library Circulation",
			{
				"member": self.member,
				"book_copy": self.book_copy,
				"docstatus": 1,
				"transaction_type": "Issue",
				"return_date": ["is", "not set"]
			}
		)
		
		if existing_issue:
			frappe.throw(_("Book Copy {0} is already issued to member {1}").format(
				frappe.bold(self.book_copy),
				frappe.bold(self.member_name or self.member)
			))
	
	def validate_return(self):
		"""Validate return transaction"""
		# Check if book is actually issued to this member
		issue_record = frappe.db.get_value(
			"Library Circulation",
			{
				"member": self.member,
				"book_copy": self.book_copy,
				"docstatus": 1,
				"transaction_type": "Issue",
				"return_date": ["is", "not set"]
			},
			["name", "due_date"],
			as_dict=True
		)
		
		if not issue_record:
			frappe.throw(_("No active issue record found for Book Copy {0} and Member {1}").format(
				frappe.bold(self.book_copy),
				frappe.bold(self.member_name or self.member)
			))
		
		self.issue_record = issue_record.name
		
		# Set due date from issue record
		if not self.due_date and issue_record.due_date:
			self.due_date = issue_record.due_date
		
		# Set return date if not set
		if not self.return_date:
			self.return_date = today()
	
	def validate_renewal(self):
		"""Validate renewal transaction"""
		# Check if book is actually issued to this member
		issue_record = frappe.db.get_value(
			"Library Circulation",
			{
				"member": self.member,
				"book_copy": self.book_copy,
				"docstatus": 1,
				"transaction_type": "Issue",
				"return_date": ["is", "not set"]
			},
			["name", "due_date"],
			as_dict=True
		)
		
		if not issue_record:
			frappe.throw(_("No active issue record found for Book Copy {0} and Member {1}").format(
				frappe.bold(self.book_copy),
				frappe.bold(self.member_name or self.member)
			))
		
		self.issue_record = issue_record.name
		
		# Get renewal period from settings
		renewal_period = frappe.db.get_single_value("Library Settings", "default_loan_period") or 14
		
		# Set new due date
		self.due_date = add_days(issue_record.due_date, renewal_period)
	
	def issue_book(self):
		"""Update book copy status to Issued"""
		frappe.db.set_value("Library Book Copy", self.book_copy, "status", "Issued")
		
		# Create library fine record if applicable
		if self.fine_amount and self.fine_amount > 0:
			self.create_fine_record()
	
	def return_book(self):
		"""Update book copy status to Available and mark issue record as returned"""
		frappe.db.set_value("Library Book Copy", self.book_copy, "status", "Available")
		
		# Update issue record with return date
		if self.issue_record:
			frappe.db.set_value("Library Circulation", self.issue_record, "return_date", self.return_date)
		
		# Create library fine record if applicable
		if self.fine_amount and self.fine_amount > 0:
			self.create_fine_record()
	
	def renew_book(self):
		"""Update issue record with new due date"""
		if self.issue_record:
			frappe.db.set_value("Library Circulation", self.issue_record, "due_date", self.due_date)
	
	def revert_transaction(self):
		"""Revert changes made by transaction on cancel"""
		if self.transaction_type == "Issue":
			# Set book status back to Available
			frappe.db.set_value("Library Book Copy", self.book_copy, "status", "Available")
		
		elif self.transaction_type == "Return":
			# Set book status back to Issued
			frappe.db.set_value("Library Book Copy", self.book_copy, "status", "Issued")
			
			# Clear return date from issue record
			if self.issue_record:
				frappe.db.set_value("Library Circulation", self.issue_record, "return_date", None)
		
		elif self.transaction_type == "Renew":
			# Restore original due date from issue record
			# This would require storing the original due date, which we don't have
			# For now, just log a warning
			frappe.msgprint(_("Please manually update the due date of the original issue record"))
	
	def create_fine_record(self):
		"""Create a Library Fine record"""
		fine = frappe.get_doc({
			"doctype": "Library Fine",
			"member": self.member,
			"book_copy": self.book_copy,
			"circulation": self.name,
			"fine_date": today(),
			"overdue_days": self.overdue_days,
			"fine_amount": self.fine_amount,
			"paid": 0
		})
		fine.insert(ignore_permissions=True)
		frappe.msgprint(_("Fine of {0} created for {1} overdue days").format(
			frappe.bold(self.fine_amount),
			frappe.bold(self.overdue_days)
		))
