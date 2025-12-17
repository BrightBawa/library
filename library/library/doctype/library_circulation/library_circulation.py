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
"""Validate that the library member is active and has valid membership"""
if not self.member:
frappe.throw(_("Library Member is required"))

member = frappe.get_doc("Library Member", self.member)

if member.membership_status != "Active":
frappe.throw(_("Member {0} does not have an active membership").format(self.member))

def validate_book_copy(self):
"""Validate that the book copy exists and is available for the transaction"""
if not self.book_copy:
frappe.throw(_("Book Copy is required"))

book_copy = frappe.get_doc("Library Book Copy", self.book_copy)

if self.transaction_type == "Issue":
if book_copy.status != "Available":
frappe.throw(_("Book Copy {0} is not available for issue. Current status: {1}").format(
self.book_copy, book_copy.status))

def set_defaults(self):
"""Set default values for the document"""
if not self.transaction_date:
self.transaction_date = today()

if not self.librarian:
self.librarian = frappe.session.user

# Get settings
settings = frappe.get_single("Library Settings")

if self.transaction_type == "Issue" and not self.issue_date:
self.issue_date = self.transaction_date

if self.transaction_type == "Issue" and not self.due_date:
# Try to get loan period from membership type first, fallback to settings
loan_period = settings.default_loan_period or 14
if self.membership_type:
membership_type = frappe.get_doc("Library Membership Type", self.membership_type)
loan_period = membership_type.loan_period_days or loan_period
self.due_date = add_days(self.issue_date, loan_period)

# Get max renewals from settings
if not self.max_renewals_allowed:
self.max_renewals_allowed = settings.max_renewals or 0

def calculate_overdue(self):
"""Calculate days overdue and fine amount"""
if self.return_date and self.due_date:
overdue_days = date_diff(self.return_date, self.due_date)
if overdue_days > 0:
self.days_overdue = overdue_days

# Calculate fine - try membership type first, then settings
settings = frappe.get_single("Library Settings")
fine_per_day = settings.default_fine_per_day or 0

if self.membership_type:
membership_type = frappe.get_doc("Library Membership Type", self.membership_type)
fine_per_day = membership_type.fine_per_day or fine_per_day

self.fine_amount = self.days_overdue * fine_per_day
else:
self.days_overdue = 0
self.fine_amount = 0

def validate_issue(self):
"""Validate book issue transaction"""
# Check if member has reached maximum books limit
member = frappe.get_doc("Library Member", self.member)
membership_type = frappe.get_doc("Library Membership Type", member.membership_type)

max_books = membership_type.max_books_allowed or 0
current_books = member.books_issued or 0

if current_books >= max_books:
frappe.throw(_("Member {0} has already issued {1} books. Maximum allowed: {2}").format(
self.member, current_books, max_books))

# Check if member has any overdue books
overdue_books = frappe.db.count("Library Circulation", {
"member": self.member,
"docstatus": 1,
"return_date": ["is", "not set"],
"due_date": ["<", today()]
})

if overdue_books > 0:
frappe.msgprint(_("Warning: Member {0} has {1} overdue book(s).").format(
self.member, overdue_books), alert=True)

def validate_return(self):
"""Validate book return transaction"""
if not self.return_date:
self.return_date = today()

# Find the original issue transaction
issue_transaction = frappe.db.get_value("Library Circulation", {
"member": self.member,
"book_copy": self.book_copy,
"transaction_type": "Issue",
"docstatus": 1,
"return_date": ["is", "not set"]
}, ["name", "issue_date", "due_date"], as_dict=1)

if not issue_transaction:
frappe.throw(_("No active issue transaction found for this book copy and member"))

# Set issue and due dates from original transaction
self.issue_date = issue_transaction.issue_date
self.due_date = issue_transaction.due_date

def validate_renewal(self):
"""Validate book renewal transaction"""
# Find the original issue transaction
issue_transaction = frappe.db.get_value("Library Circulation", {
"member": self.member,
"book_copy": self.book_copy,
"transaction_type": ["in", ["Issue", "Renew"]],
"docstatus": 1,
"return_date": ["is", "not set"]
}, ["name", "issue_date", "due_date", "renewal_count", "max_renewals_allowed"], as_dict=1)

if not issue_transaction:
frappe.throw(_("No active issue transaction found for this book copy and member"))

# Check if renewal limit reached
renewal_count = issue_transaction.renewal_count or 0
max_renewals = issue_transaction.max_renewals_allowed or 0

if renewal_count >= max_renewals:
frappe.throw(_("Maximum renewal limit ({0}) reached for this book").format(max_renewals))

# Set values from original transaction
self.issue_date = issue_transaction.issue_date
self.renewal_count = renewal_count + 1

def issue_book(self):
"""Process book issue"""
# Update book copy status
book_copy = frappe.get_doc("Library Book Copy", self.book_copy)
book_copy.status = "Issued"
book_copy.save(ignore_permissions=True)

# Update member's books issued count
frappe.db.set_value("Library Member", self.member, "books_issued", 
frappe.db.get_value("Library Member", self.member, "books_issued") + 1)

def return_book(self):
"""Process book return"""
# Update the original issue transaction
issue_transaction = frappe.db.get_value("Library Circulation", {
"member": self.member,
"book_copy": self.book_copy,
"transaction_type": "Issue",
"docstatus": 1,
"return_date": ["is", "not set"]
})

if issue_transaction:
frappe.db.set_value("Library Circulation", issue_transaction, "return_date", self.return_date)

# Update book copy status
book_copy = frappe.get_doc("Library Book Copy", self.book_copy)
book_copy.status = "Available"
book_copy.save(ignore_permissions=True)

# Update member's books issued count
current_books = frappe.db.get_value("Library Member", self.member, "books_issued") or 0
if current_books > 0:
frappe.db.set_value("Library Member", self.member, "books_issued", current_books - 1)

# Create fine record if overdue
if self.fine_amount and self.fine_amount > 0:
fine = frappe.get_doc({
"doctype": "Library Fine",
"member": self.member,
"fine_date": today(),
"fine_type": "Overdue",
"circulation": self.name,
"fine_amount": self.fine_amount,
"outstanding_amount": self.fine_amount,
"payment_status": "Unpaid"
})
fine.insert(ignore_permissions=True)

frappe.msgprint(_("Fine of {0} created for {1} days overdue").format(
self.fine_amount, self.days_overdue))

def renew_book(self):
"""Process book renewal"""
# Update the original transaction
original_transaction = frappe.db.get_value("Library Circulation", {
"member": self.member,
"book_copy": self.book_copy,
"transaction_type": ["in", ["Issue", "Renew"]],
"docstatus": 1,
"return_date": ["is", "not set"]
})

if original_transaction:
frappe.db.set_value("Library Circulation", original_transaction, {
"return_date": today(),
"renewal_count": self.renewal_count
})

# Set new due date
settings = frappe.get_single("Library Settings")
loan_period = settings.default_loan_period or 14

# Try to get loan period from membership type first
if self.membership_type:
membership_type = frappe.get_doc("Library Membership Type", self.membership_type)
loan_period = membership_type.loan_period_days or loan_period

self.due_date = add_days(today(), loan_period)

def revert_transaction(self):
"""Revert the transaction on cancel"""
if self.transaction_type == "Issue":
# Revert book copy status
book_copy = frappe.get_doc("Library Book Copy", self.book_copy)
book_copy.status = "Available"
book_copy.save(ignore_permissions=True)

# Revert member's books issued count
current_books = frappe.db.get_value("Library Member", self.member, "books_issued") or 0
if current_books > 0:
frappe.db.set_value("Library Member", self.member, "books_issued", current_books - 1)

elif self.transaction_type == "Return":
# Revert book copy status
book_copy = frappe.get_doc("Library Book Copy", self.book_copy)
book_copy.status = "Issued"
book_copy.save(ignore_permissions=True)

# Revert member's books issued count
frappe.db.set_value("Library Member", self.member, "books_issued", 
frappe.db.get_value("Library Member", self.member, "books_issued") + 1)

# Delete or cancel associated fine if exists
fines = frappe.get_all("Library Fine", filters={"circulation": self.name})
for fine in fines:
fine_doc = frappe.get_doc("Library Fine", fine.name)
# Only delete if unpaid, otherwise just notify
if fine_doc.payment_status == "Unpaid":
fine_doc.delete()
else:
frappe.msgprint(_("Note: Fine {0} was not automatically deleted because payment was recorded").format(fine.name), alert=True)
