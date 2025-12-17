"""
Library Circulation API
Handles book issue, return, renewal, and fine calculations
"""

import frappe
from frappe import _
from frappe.utils import today, add_days, date_diff, get_datetime, nowdate
from datetime import datetime


@frappe.whitelist()
def issue_book(member, book_copy, issue_date=None):
	"""Issue a book to a member"""
	# Input validation
	if not member or not isinstance(member, str):
		frappe.throw(_("Invalid member parameter"))
	if not book_copy or not isinstance(book_copy, str):
		frappe.throw(_("Invalid book_copy parameter"))
	
	# Sanitize inputs
	member = frappe.utils.cstr(member).strip()
	book_copy = frappe.utils.cstr(book_copy).strip()
	
	if not issue_date:
		issue_date = today()
	
	# Validate date format
	try:
		if issue_date:
			from frappe.utils import getdate
			issue_date = getdate(issue_date)
	except:
		frappe.throw(_("Invalid date format"))
	
	# Permission check
	if not frappe.has_permission("Library Circulation", "create"):
		frappe.throw(_("Insufficient permissions to issue books"))
	
	# Validate member exists
	if not frappe.db.exists("Library Member", member):
		frappe.throw(_("Library Member {0} does not exist").format(member))
	
	# Validate book copy exists
	if not frappe.db.exists("Library Book Copy", book_copy):
		frappe.throw(_("Book Copy {0} does not exist").format(book_copy))
	
	# Validate member
	member_doc = frappe.get_doc("Library Member", member)
	validate_member(member_doc)
	
	# Validate book copy
	copy_doc = frappe.get_doc("Library Book Copy", book_copy)
	if copy_doc.status != "Available":
		frappe.throw(_("Book copy {0} is not available. Current status: {1}").format(
			book_copy, copy_doc.status
		))
	
	# Check if member has reached max books limit
	check_max_books_limit(member_doc)
	
	# Get loan period from membership type
	membership_type = frappe.get_doc("Library Membership Type", member_doc.membership_type)
	due_date = add_days(issue_date, membership_type.loan_period_days)
	
	# Get max renewals from settings
	settings = frappe.get_single("Library Settings")
	max_renewals = settings.max_renewals or 3
	
	# Create circulation record
	circulation = frappe.get_doc({
		"doctype": "Library Circulation",
		"transaction_type": "Issue",
		"transaction_date": issue_date,
		"member": member,
		"book_copy": book_copy,
		"issue_date": issue_date,
		"due_date": due_date,
		"condition_on_issue": copy_doc.condition,
		"max_renewals_allowed": max_renewals,
		"renewal_count": 0
	})
	
	circulation.insert()
	circulation.submit()
	
	# Update book copy status
	copy_doc.status = "Issued"
	copy_doc.save(ignore_permissions=True)
	
	# Update book and member stats
	update_book_stats(copy_doc.book)
	update_member_stats(member)
	
	frappe.db.commit()
	
	return circulation.name


@frappe.whitelist()
def return_book(circulation, return_date=None, condition=None):
	"""Return a book"""
	# Input validation
	if not circulation or not isinstance(circulation, str):
		frappe.throw(_("Invalid circulation parameter"))
	
	# Sanitize inputs
	circulation = frappe.utils.cstr(circulation).strip()
	if condition:
		condition = frappe.utils.cstr(condition).strip()
		# Validate condition value
		valid_conditions = ["Good", "Fair", "Damaged", "Lost"]
		if condition not in valid_conditions:
			frappe.throw(_("Invalid condition value. Must be one of: {0}").format(", ".join(valid_conditions)))
	
	if not return_date:
		return_date = today()
	else:
		# Validate date format
		try:
			from frappe.utils import getdate
			return_date = getdate(return_date)
		except:
			frappe.throw(_("Invalid date format"))
	
	# Permission check
	if not frappe.has_permission("Library Circulation", "write"):
		frappe.throw(_("Insufficient permissions to return books"))
	
	# Validate circulation exists
	if not frappe.db.exists("Library Circulation", circulation):
		frappe.throw(_("Circulation record {0} does not exist").format(circulation))
	
	circulation_doc = frappe.get_doc("Library Circulation", circulation)
	
	if circulation_doc.return_date:
		frappe.throw(_("This book has already been returned"))
	
	# Update circulation
	circulation_doc.return_date = return_date
	if condition:
		circulation_doc.condition_on_return = condition
	
	# Calculate overdue days and fine
	if get_datetime(return_date) > get_datetime(circulation_doc.due_date):
		circulation_doc.days_overdue = date_diff(return_date, circulation_doc.due_date)
		
		# Calculate fine if enabled
		settings = frappe.get_single("Library Settings")
		if settings.enable_fines:
			fine_amount = calculate_fine(circulation_doc)
			if fine_amount > 0:
				circulation_doc.fine_amount = fine_amount
				create_fine_record(circulation_doc, fine_amount)
	
	circulation_doc.save(ignore_permissions=True)
	
	# Update book copy status
	copy_doc = frappe.get_doc("Library Book Copy", circulation_doc.book_copy)
	
	# Check if condition changed
	if condition and condition == "Damaged":
		copy_doc.status = "Damaged"
		copy_doc.condition = "Damaged"
		# Create damage fine
		create_damage_fine(circulation_doc)
	else:
		copy_doc.status = "Available"
		if condition:
			copy_doc.condition = condition
	
	copy_doc.save(ignore_permissions=True)
	
	# Update book and member stats
	update_book_stats(copy_doc.book)
	update_member_stats(circulation_doc.member)
	
	# Check for reservations
	check_and_notify_reservations(copy_doc.book)
	
	frappe.db.commit()
	
	return circulation_doc.name


@frappe.whitelist()
def renew_book(circulation):
	"""Renew a book"""
	# Input validation
	if not circulation or not isinstance(circulation, str):
		frappe.throw(_("Invalid circulation parameter"))
	
	# Sanitize input
	circulation = frappe.utils.cstr(circulation).strip()
	
	# Permission check
	if not frappe.has_permission("Library Circulation", "write"):
		frappe.throw(_("Insufficient permissions to renew books"))
	
	# Validate circulation exists
	if not frappe.db.exists("Library Circulation", circulation):
		frappe.throw(_("Circulation record {0} does not exist").format(circulation))
	
	circulation_doc = frappe.get_doc("Library Circulation", circulation)
	
	if circulation_doc.return_date:
		frappe.throw(_("Cannot renew a returned book"))
	
	# Check renewal limit
	if circulation_doc.renewal_count >= circulation_doc.max_renewals_allowed:
		frappe.throw(_("Maximum renewals ({0}) reached").format(
			circulation_doc.max_renewals_allowed
		))
	
	# Check if book is reserved by someone else
	if has_active_reservation(circulation_doc.book, circulation_doc.member):
		frappe.throw(_("This book is reserved by another member"))
	
	# Get loan period
	member_doc = frappe.get_doc("Library Member", circulation_doc.member)
	membership_type = frappe.get_doc("Library Membership Type", member_doc.membership_type)
	
	# Calculate new due date from current due date
	new_due_date = add_days(circulation_doc.due_date, membership_type.loan_period_days)
	
	# Create renewal transaction
	renewal = frappe.get_doc({
		"doctype": "Library Circulation",
		"transaction_type": "Renew",
		"transaction_date": today(),
		"member": circulation_doc.member,
		"book_copy": circulation_doc.book_copy,
		"issue_date": circulation_doc.issue_date,
		"due_date": new_due_date,
		"renewal_count": circulation_doc.renewal_count + 1,
		"max_renewals_allowed": circulation_doc.max_renewals_allowed
	})
	
	renewal.insert()
	renewal.submit()
	
	# Update original circulation
	circulation_doc.renewal_count += 1
	circulation_doc.due_date = new_due_date
	circulation_doc.save(ignore_permissions=True)
	
	frappe.db.commit()
	
	return renewal.name


def validate_member(member_doc):
	"""Validate if member can borrow books"""
	if member_doc.membership_status != "Active":
		frappe.throw(_("Member {0} is not active. Status: {1}").format(
			member_doc.full_name, member_doc.membership_status
		))
	
	# Check membership expiry
	if member_doc.membership_end_date and get_datetime(member_doc.membership_end_date) < get_datetime(today()):
		frappe.throw(_("Membership has expired on {0}").format(member_doc.membership_end_date))
	
	# Check outstanding balance
	if member_doc.outstanding_balance and member_doc.outstanding_balance > 0:
		frappe.msgprint(_("Warning: Member has outstanding balance of {0}").format(
			member_doc.outstanding_balance
		), indicator="orange")


def check_max_books_limit(member_doc):
	"""Check if member has reached maximum books limit"""
	membership_type = frappe.get_doc("Library Membership Type", member_doc.membership_type)
	
	if member_doc.books_issued >= membership_type.max_books_allowed:
		frappe.throw(_("Maximum books limit ({0}) reached").format(
			membership_type.max_books_allowed
		))


def calculate_fine(circulation_doc):
	"""Calculate fine for overdue book"""
	if circulation_doc.days_overdue <= 0:
		return 0
	
	# Get fine rate from membership type
	member_doc = frappe.get_doc("Library Member", circulation_doc.member)
	membership_type = frappe.get_doc("Library Membership Type", member_doc.membership_type)
	
	fine_per_day = membership_type.fine_per_day or 0
	total_fine = circulation_doc.days_overdue * fine_per_day
	
	return total_fine


def create_fine_record(circulation_doc, amount):
	"""Create a fine record"""
	fine = frappe.get_doc({
		"doctype": "Library Fine",
		"member": circulation_doc.member,
		"circulation": circulation_doc.name,
		"fine_type": "Overdue",
		"fine_date": today(),
		"fine_amount": amount,
		"paid_amount": 0,
		"outstanding_amount": amount,
		"payment_status": "Unpaid"
	})
	
	fine.insert(ignore_permissions=True)
	
	# Update member outstanding balance
	update_member_stats(circulation_doc.member)


def create_damage_fine(circulation_doc):
	"""Create fine for damaged book"""
	settings = frappe.get_single("Library Settings")
	damage_fine = settings.damage_fine_amount or 50.00
	
	fine = frappe.get_doc({
		"doctype": "Library Fine",
		"member": circulation_doc.member,
		"circulation": circulation_doc.name,
		"fine_type": "Damage",
		"fine_date": today(),
		"fine_amount": damage_fine,
		"paid_amount": 0,
		"outstanding_amount": damage_fine,
		"payment_status": "Unpaid"
	})
	
	fine.insert(ignore_permissions=True)
	
	# Update member outstanding balance
	update_member_stats(circulation_doc.member)


def update_book_stats(book):
	"""Update book statistics"""
	# Count total and available copies
	stats = frappe.db.sql("""
		SELECT 
			COUNT(*) as total_copies,
			SUM(CASE WHEN status = 'Available' THEN 1 ELSE 0 END) as available_copies
		FROM `tabLibrary Book Copy`
		WHERE book = %s
	""", book, as_dict=True)
	
	if stats:
		book_doc = frappe.get_doc("Library Book", book)
		book_doc.total_copies = stats[0].total_copies
		book_doc.available_copies = stats[0].available_copies
		
		# Update book status
		if book_doc.available_copies == 0:
			book_doc.book_status = "All Issued"
		elif book_doc.available_copies > 0:
			book_doc.book_status = "Available"
		
		book_doc.save(ignore_permissions=True)


def update_member_stats(member):
	"""Update member statistics"""
	# Get current books issued
	books_issued = frappe.db.count("Library Circulation", {
		"member": member,
		"docstatus": 1,
		"return_date": ["is", "not set"],
		"transaction_type": ["in", ["Issue", "Renew"]]
	})
	
	# Get total books borrowed
	total_borrowed = frappe.db.count("Library Circulation", {
		"member": member,
		"docstatus": 1,
		"transaction_type": "Issue"
	})
	
	# Get overdue books
	overdue = frappe.db.count("Library Circulation", {
		"member": member,
		"docstatus": 1,
		"return_date": ["is", "not set"],
		"due_date": ["<", today()]
	})
	
	# Get outstanding balance
	outstanding = frappe.db.get_value(
		"Library Fine",
		{"member": member, "payment_status": ["in", ["Unpaid", "Partially Paid"]]},
		"SUM(outstanding_amount)"
	) or 0
	
	# Update member
	member_doc = frappe.get_doc("Library Member", member)
	member_doc.books_issued = books_issued
	member_doc.total_books_borrowed = total_borrowed
	member_doc.overdue_books = overdue
	member_doc.outstanding_balance = outstanding
	member_doc.save(ignore_permissions=True)


def has_active_reservation(book, exclude_member=None):
	"""Check if book has active reservations by other members"""
	filters = {
		"book": book,
		"status": "Active"
	}
	
	if exclude_member:
		filters["member"] = ["!=", exclude_member]
	
	return frappe.db.exists("Library Reservation", filters)


def check_and_notify_reservations(book):
	"""Check for active reservations and notify first in queue"""
	reservations = frappe.get_all(
		"Library Reservation",
		filters={"book": book, "status": "Active"},
		fields=["name", "member"],
		order_by="priority asc, reservation_date asc",
		limit=1
	)
	
	if reservations:
		# Send notification to member
		reservation = frappe.get_doc("Library Reservation", reservations[0].name)
		send_book_available_notification(reservation)


def send_book_available_notification(reservation):
	"""Send email notification that reserved book is available"""
	member = frappe.get_doc("Library Member", reservation.member)
	book = frappe.get_doc("Library Book", reservation.book)
	
	if not member.email:
		return
	
	settings = frappe.get_single("Library Settings")
	expiry_date = add_days(today(), settings.reservation_expiry_days or 3)
	
	# Update reservation
	reservation.notified_date = today()
	reservation.expiry_date = expiry_date
	reservation.save(ignore_permissions=True)
	
	# Send email
	subject = _("Reserved Book Available: {0}").format(book.book_title)
	message = _("""
		<p>Dear {member_name},</p>
		
		<p>Good news! The book you reserved is now available:</p>
		
		<p><strong>{book_title}</strong> by {author}</p>
		
		<p>Please collect it from the library by <strong>{expiry_date}</strong>.</p>
		
		<p>If not collected by the expiry date, the reservation will be cancelled.</p>
		
		<p>Thank you,<br>Library Team</p>
	""").format(
		member_name=member.full_name,
		book_title=book.book_title,
		author=book.author,
		expiry_date=expiry_date
	)
	
	frappe.sendmail(
		recipients=[member.email],
		subject=subject,
		message=message
	)


@frappe.whitelist()
def send_overdue_reminders():
	"""Send reminder emails for overdue books (scheduled daily)"""
	settings = frappe.get_single("Library Settings")
	
	if not settings.send_overdue_reminders:
		return
	
	reminder_days = settings.overdue_reminder_days or 1
	
	# Get overdue circulations
	overdue_circulations = frappe.db.sql("""
		SELECT 
			lc.name, lc.member, lc.book_copy, lc.due_date,
			DATEDIFF(CURDATE(), lc.due_date) as days_overdue
		FROM `tabLibrary Circulation` lc
		WHERE lc.docstatus = 1
			AND lc.return_date IS NULL
			AND lc.due_date < CURDATE()
			AND DATEDIFF(CURDATE(), lc.due_date) >= %s
	""", reminder_days, as_dict=True)
	
	for circulation in overdue_circulations:
		send_overdue_reminder(circulation)
	
	return len(overdue_circulations)


def send_overdue_reminder(circulation_data):
	"""Send overdue reminder email to member"""
	member = frappe.get_doc("Library Member", circulation_data.member)
	
	if not member.email:
		return
	
	copy = frappe.get_doc("Library Book Copy", circulation_data.book_copy)
	book = frappe.get_doc("Library Book", copy.book)
	
	subject = _("Overdue Book Reminder: {0}").format(book.book_title)
	message = _("""
		<p>Dear {member_name},</p>
		
		<p>This is a reminder that the following book is <strong>overdue</strong>:</p>
		
		<p><strong>{book_title}</strong> by {author}</p>
		<p>Due Date: <strong>{due_date}</strong> ({days_overdue} days overdue)</p>
		
		<p>Please return the book to the library as soon as possible to avoid additional fines.</p>
		
		<p>Thank you,<br>Library Team</p>
	""").format(
		member_name=member.full_name,
		book_title=book.book_title,
		author=book.author,
		due_date=circulation_data.due_date,
		days_overdue=circulation_data.days_overdue
	)
	
	frappe.sendmail(
		recipients=[member.email],
		subject=subject,
		message=message
	)


@frappe.whitelist()
def auto_calculate_fines():
	"""Auto-calculate fines for overdue books (scheduled daily)"""
	settings = frappe.get_single("Library Settings")
	
	if not settings.enable_fines:
		return
	
	# Get overdue circulations without return date
	overdue_circulations = frappe.db.sql("""
		SELECT name, member, days_overdue, fine_amount
		FROM `tabLibrary Circulation`
		WHERE docstatus = 1
			AND return_date IS NULL
			AND due_date < CURDATE()
	""", as_dict=True)
	
	for circulation in overdue_circulations:
		circulation_doc = frappe.get_doc("Library Circulation", circulation.name)
		
		# Recalculate days overdue
		circulation_doc.days_overdue = date_diff(today(), circulation_doc.due_date)
		
		# Calculate new fine
		new_fine = calculate_fine(circulation_doc)
		
		if new_fine != circulation.fine_amount:
			circulation_doc.fine_amount = new_fine
			circulation_doc.save(ignore_permissions=True)
			
			# Update or create fine record
			existing_fine = frappe.db.get_value(
				"Library Fine",
				{"circulation": circulation.name, "fine_type": "Overdue"},
				"name"
			)
			
			if existing_fine:
				fine_doc = frappe.get_doc("Library Fine", existing_fine)
				fine_doc.fine_amount = new_fine
				fine_doc.outstanding_amount = new_fine - fine_doc.paid_amount
				fine_doc.save(ignore_permissions=True)
			else:
				create_fine_record(circulation_doc, new_fine)
	
	frappe.db.commit()
	
	return len(overdue_circulations)


@frappe.whitelist()
def expire_unclaimed_reservations():
	"""Expire reservations that weren't claimed (scheduled daily)"""
	# Get expired reservations
	expired = frappe.db.sql("""
		SELECT name
		FROM `tabLibrary Reservation`
		WHERE status = 'Active'
			AND expiry_date IS NOT NULL
			AND expiry_date < CURDATE()
	""", as_dict=True)
	
	for reservation in expired:
		res_doc = frappe.get_doc("Library Reservation", reservation.name)
		res_doc.status = "Expired"
		res_doc.save(ignore_permissions=True)
		
		# Check for next reservation
		check_and_notify_reservations(res_doc.book)
	
	frappe.db.commit()
	
	return len(expired)
