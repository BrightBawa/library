"""
Library Reports API
Provides data for various library reports and dashboards
"""

import frappe
from frappe import _
from frappe.utils import today, getdate, add_days, date_diff


@frappe.whitelist()
def get_circulation_report(from_date=None, to_date=None, member=None, book=None):
	"""Get circulation report with filters"""
	# Permission check
	if not frappe.has_permission("Library Circulation", "read"):
		frappe.throw(_("Insufficient permissions to view circulation reports"))
	
	# Input validation and sanitization
	if member:
		member = frappe.utils.cstr(member).strip()
		if not frappe.db.exists("Library Member", member):
			frappe.throw(_("Library Member {0} does not exist").format(member))
	
	if book:
		book = frappe.utils.cstr(book).strip()
		if not frappe.db.exists("Library Book", book):
			frappe.throw(_("Library Book {0} does not exist").format(book))
	
	# Validate dates
	if not from_date:
		from_date = add_days(today(), -30)
	else:
		try:
			from frappe.utils import getdate
			from_date = getdate(from_date)
		except:
			frappe.throw(_("Invalid from_date format"))
	
	if not to_date:
		to_date = today()
	else:
		try:
			from frappe.utils import getdate
			to_date = getdate(to_date)
		except:
			frappe.throw(_("Invalid to_date format"))
	
	# Validate date range
	if from_date > to_date:
		frappe.throw(_("From date cannot be greater than to date"))
	
	filters = {
		"docstatus": 1,
		"transaction_date": ["between", [from_date, to_date]]
	}
	
	if member:
		filters["member"] = member
	if book:
		filters["book"] = book
	
	# Build WHERE conditions properly to prevent SQL injection
	conditions = ["lc.docstatus = 1", "lc.transaction_date BETWEEN %(from_date)s AND %(to_date)s"]
	params = {"from_date": from_date, "to_date": to_date}
	
	if member:
		conditions.append("lc.member = %(member)s")
		params["member"] = member
	
	if book:
		conditions.append("lbc.book = %(book)s")
		params["book"] = book
	
	where_clause = " AND ".join(conditions)
	
	data = frappe.db.sql("""
		SELECT 
			lc.name,
			lc.transaction_type,
			lc.transaction_date,
			lc.member,
			lm.full_name as member_name,
			lc.book_copy,
			lbc.book as book,
			lb.book_title,
			lb.author,
			lc.issue_date,
			lc.due_date,
			lc.return_date,
			lc.renewal_count,
			lc.days_overdue,
			lc.fine_amount,
			lc.condition_on_return
		FROM `tabLibrary Circulation` lc
		INNER JOIN `tabLibrary Member` lm ON lc.member = lm.name
		INNER JOIN `tabLibrary Book Copy` lbc ON lc.book_copy = lbc.name
		INNER JOIN `tabLibrary Book` lb ON lbc.book = lb.name
		WHERE {where_clause}
		ORDER BY lc.transaction_date DESC, lc.creation DESC
	""".format(where_clause=where_clause), params, as_dict=True)
	
	return data


@frappe.whitelist()
def get_overdue_books_report():
	"""Get all overdue books with member details"""
	# Permission check
	if not frappe.has_permission("Library Circulation", "read"):
		frappe.throw(_("Insufficient permissions to view overdue reports"))
	
	data = frappe.db.sql("""
		SELECT 
			lc.name as circulation_id,
			lc.member,
			lm.full_name as member_name,
			lm.email,
			lm.phone,
			lm.membership_type,
			lbc.book,
			lb.book_title,
			lb.author,
			lb.isbn,
			lbc.barcode,
			lbc.location,
			lc.issue_date,
			lc.due_date,
			DATEDIFF(CURDATE(), lc.due_date) as days_overdue,
			lc.fine_amount,
			lc.renewal_count,
			lc.max_renewals_allowed
		FROM `tabLibrary Circulation` lc
		INNER JOIN `tabLibrary Member` lm ON lc.member = lm.name
		INNER JOIN `tabLibrary Book Copy` lbc ON lc.book_copy = lbc.name
		INNER JOIN `tabLibrary Book` lb ON lbc.book = lb.name
		WHERE lc.docstatus = 1
			AND lc.return_date IS NULL
			AND lc.due_date < CURDATE()
		ORDER BY days_overdue DESC, lc.due_date ASC
	""", as_dict=True)
	
	return data


@frappe.whitelist()
def get_popular_books_report(from_date=None, to_date=None, limit=50):
	"""Get most issued books"""
	
	if not from_date:
		from_date = add_days(today(), -90)  # Last 3 months
	if not to_date:
		to_date = today()
	
	data = frappe.db.sql("""
		SELECT 
			lbc.book,
			lb.book_title,
			lb.author,
			lb.publisher,
			lb.isbn,
			lb.category,
			lc.category_name,
			COUNT(*) as issue_count,
			COUNT(DISTINCT lcirc.member) as unique_members,
			AVG(DATEDIFF(COALESCE(lcirc.return_date, CURDATE()), lcirc.issue_date)) as avg_loan_days
		FROM `tabLibrary Circulation` lcirc
		INNER JOIN `tabLibrary Book Copy` lbc ON lcirc.book_copy = lbc.name
		INNER JOIN `tabLibrary Book` lb ON lbc.book = lb.name
		LEFT JOIN `tabLibrary Category` lc ON lb.category = lc.name
		WHERE lcirc.docstatus = 1
			AND lcirc.transaction_type = 'Issue'
			AND lcirc.transaction_date BETWEEN %(from_date)s AND %(to_date)s
		GROUP BY lbc.book
		ORDER BY issue_count DESC
		LIMIT %(limit)s
	""", {"from_date": from_date, "to_date": to_date, "limit": limit}, as_dict=True)
	
	return data


@frappe.whitelist()
def get_member_activity_report(member):
	"""Get detailed activity report for a specific member"""
	# Permission check
	if not frappe.has_permission("Library Member", "read"):
		frappe.throw(_("Insufficient permissions to view member reports"))
	
	# Input validation
	if not member or not isinstance(member, str):
		frappe.throw(_("Invalid member parameter"))
	
	# Sanitize input
	member = frappe.utils.cstr(member).strip()
	
	# Validate member exists
	if not frappe.db.exists("Library Member", member):
		frappe.throw(_("Library Member {0} does not exist").format(member))
	
	# Get member details
	member_doc = frappe.get_doc("Library Member", member)
	
	# Get borrowing history
	history = frappe.db.sql("""
		SELECT 
			lc.transaction_type,
			lc.transaction_date,
			lbc.book,
			lb.book_title,
			lb.author,
			lc.issue_date,
			lc.due_date,
			lc.return_date,
			lc.days_overdue,
			lc.fine_amount,
			lc.renewal_count
		FROM `tabLibrary Circulation` lc
		INNER JOIN `tabLibrary Book Copy` lbc ON lc.book_copy = lbc.name
		INNER JOIN `tabLibrary Book` lb ON lbc.book = lb.name
		WHERE lc.member = %(member)s
			AND lc.docstatus = 1
		ORDER BY lc.transaction_date DESC, lc.creation DESC
	""", {"member": member}, as_dict=True)
	
	# Get current issues
	current_issues = frappe.db.sql("""
		SELECT 
			lbc.book,
			lb.book_title,
			lb.author,
			lc.issue_date,
			lc.due_date,
			DATEDIFF(CURDATE(), lc.due_date) as days_status,
			lc.renewal_count,
			lc.max_renewals_allowed
		FROM `tabLibrary Circulation` lc
		INNER JOIN `tabLibrary Book Copy` lbc ON lc.book_copy = lbc.name
		INNER JOIN `tabLibrary Book` lb ON lbc.book = lb.name
		WHERE lc.member = %(member)s
			AND lc.docstatus = 1
			AND lc.return_date IS NULL
		ORDER BY lc.due_date ASC
	""", {"member": member}, as_dict=True)
	
	# Get active reservations
	reservations = frappe.db.sql("""
		SELECT 
			lr.book,
			lb.book_title,
			lb.author,
			lr.reservation_date,
			lr.expiry_date,
			lr.status,
			lr.priority
		FROM `tabLibrary Reservation` lr
		INNER JOIN `tabLibrary Book` lb ON lr.book = lb.name
		WHERE lr.member = %(member)s
			AND lr.status IN ('Active', 'Notified')
		ORDER BY lr.reservation_date DESC
	""", {"member": member}, as_dict=True)
	
	# Get outstanding fines
	fines = frappe.db.sql("""
		SELECT 
			lf.fine_type,
			lf.fine_date,
			lf.fine_amount,
			lf.paid_amount,
			lf.outstanding_amount,
			lf.payment_status,
			lc.book_copy,
			lbc.book,
			lb.book_title
		FROM `tabLibrary Fine` lf
		LEFT JOIN `tabLibrary Circulation` lc ON lf.circulation = lc.name
		LEFT JOIN `tabLibrary Book Copy` lbc ON lc.book_copy = lbc.name
		LEFT JOIN `tabLibrary Book` lb ON lbc.book = lb.name
		WHERE lf.member = %(member)s
			AND lf.payment_status IN ('Unpaid', 'Partially Paid')
		ORDER BY lf.fine_date DESC
	""", {"member": member}, as_dict=True)
	
	return {
		"member": member_doc.as_dict(),
		"borrowing_history": history,
		"current_issues": current_issues,
		"active_reservations": reservations,
		"outstanding_fines": fines
	}


@frappe.whitelist()
def get_fine_collection_report(from_date=None, to_date=None):
	"""Get fine collection report"""
	
	if not from_date:
		from_date = add_days(today(), -30)
	if not to_date:
		to_date = today()
	
	# Get fines summary
	summary = frappe.db.sql("""
		SELECT 
			fine_type,
			COUNT(*) as fine_count,
			SUM(fine_amount) as total_fines,
			SUM(paid_amount) as total_paid,
			SUM(outstanding_amount) as total_outstanding,
			SUM(CASE WHEN payment_status = 'Paid' THEN 1 ELSE 0 END) as paid_count,
			SUM(CASE WHEN payment_status = 'Unpaid' THEN 1 ELSE 0 END) as unpaid_count,
			SUM(CASE WHEN payment_status = 'Partially Paid' THEN 1 ELSE 0 END) as partial_count,
			SUM(CASE WHEN payment_status = 'Waived' THEN 1 ELSE 0 END) as waived_count
		FROM `tabLibrary Fine`
		WHERE fine_date BETWEEN %(from_date)s AND %(to_date)s
		GROUP BY fine_type
	""", {"from_date": from_date, "to_date": to_date}, as_dict=True)
	
	# Get detailed fines
	details = frappe.db.sql("""
		SELECT 
			lf.name,
			lf.fine_type,
			lf.fine_date,
			lf.member,
			lm.full_name as member_name,
			lf.fine_amount,
			lf.paid_amount,
			lf.outstanding_amount,
			lf.payment_status,
			lf.payment_date,
			lbc.book,
			lb.book_title
		FROM `tabLibrary Fine` lf
		INNER JOIN `tabLibrary Member` lm ON lf.member = lm.name
		LEFT JOIN `tabLibrary Circulation` lc ON lf.circulation = lc.name
		LEFT JOIN `tabLibrary Book Copy` lbc ON lc.book_copy = lbc.name
		LEFT JOIN `tabLibrary Book` lb ON lbc.book = lb.name
		WHERE lf.fine_date BETWEEN %(from_date)s AND %(to_date)s
		ORDER BY lf.fine_date DESC
	""", {"from_date": from_date, "to_date": to_date}, as_dict=True)
	
	return {
		"summary": summary,
		"details": details
	}


@frappe.whitelist()
def get_library_dashboard_stats():
	"""Get KPIs for library dashboard"""
	
	# Book statistics
	book_stats = frappe.db.sql("""
		SELECT 
			COUNT(DISTINCT lb.name) as total_books,
			SUM(lb.total_copies) as total_copies,
			SUM(lb.available_copies) as available_copies,
			SUM(lb.total_copies - lb.available_copies) as issued_copies,
			COUNT(DISTINCT lb.category) as total_categories
		FROM `tabLibrary Book` lb
	""", as_dict=True)[0]
	
	# Member statistics
	member_stats = frappe.db.sql("""
		SELECT 
			COUNT(*) as total_members,
			SUM(CASE WHEN membership_status = 'Active' THEN 1 ELSE 0 END) as active_members,
			SUM(books_issued) as total_books_issued,
			SUM(overdue_books) as total_overdue,
			SUM(outstanding_balance) as total_outstanding
		FROM `tabLibrary Member`
	""", as_dict=True)[0]
	
	# Circulation statistics (last 30 days)
	thirty_days_ago = add_days(today(), -30)
	circulation_stats = frappe.db.sql("""
		SELECT 
			COUNT(*) as total_transactions,
			SUM(CASE WHEN transaction_type = 'Issue' THEN 1 ELSE 0 END) as total_issues,
			SUM(CASE WHEN transaction_type = 'Return' THEN 1 ELSE 0 END) as total_returns,
			SUM(CASE WHEN transaction_type = 'Renew' THEN 1 ELSE 0 END) as total_renewals
		FROM `tabLibrary Circulation`
		WHERE docstatus = 1
			AND transaction_date >= %(from_date)s
	""", {"from_date": thirty_days_ago}, as_dict=True)[0]
	
	# Current overdue count
	overdue_count = frappe.db.count("Library Circulation", {
		"docstatus": 1,
		"return_date": ["is", "not set"],
		"due_date": ["<", today()]
	})
	
	# Reservation statistics
	reservation_stats = frappe.db.sql("""
		SELECT 
			COUNT(*) as total_reservations,
			SUM(CASE WHEN status = 'Active' THEN 1 ELSE 0 END) as active_reservations,
			SUM(CASE WHEN status = 'Notified' THEN 1 ELSE 0 END) as notified_reservations
		FROM `tabLibrary Reservation`
	""", as_dict=True)[0]
	
	# Fine statistics
	fine_stats = frappe.db.sql("""
		SELECT 
			COUNT(*) as total_fines,
			SUM(fine_amount) as total_fine_amount,
			SUM(paid_amount) as total_paid,
			SUM(outstanding_amount) as total_outstanding,
			SUM(CASE WHEN payment_status = 'Unpaid' THEN 1 ELSE 0 END) as unpaid_count
		FROM `tabLibrary Fine`
	""", as_dict=True)[0]
	
	return {
		"books": book_stats,
		"members": member_stats,
		"circulation": circulation_stats,
		"overdue_count": overdue_count,
		"reservations": reservation_stats,
		"fines": fine_stats
	}


@frappe.whitelist()
def get_circulation_trend(days=30):
	"""Get circulation trend data for charts"""
	
	from_date = add_days(today(), -days)
	
	data = frappe.db.sql("""
		SELECT 
			DATE(transaction_date) as date,
			COUNT(*) as total,
			SUM(CASE WHEN transaction_type = 'Issue' THEN 1 ELSE 0 END) as issues,
			SUM(CASE WHEN transaction_type = 'Return' THEN 1 ELSE 0 END) as returns,
			SUM(CASE WHEN transaction_type = 'Renew' THEN 1 ELSE 0 END) as renewals
		FROM `tabLibrary Circulation`
		WHERE docstatus = 1
			AND transaction_date >= %(from_date)s
		GROUP BY DATE(transaction_date)
		ORDER BY date ASC
	""", {"from_date": from_date}, as_dict=True)
	
	return data


@frappe.whitelist()
def get_category_distribution():
	"""Get book distribution by category"""
	
	data = frappe.db.sql("""
		SELECT 
			lb.category,
			lc.category_name,
			COUNT(DISTINCT lb.name) as book_count,
			SUM(lb.total_copies) as total_copies,
			SUM(lb.available_copies) as available_copies,
			COUNT(DISTINCT lcirc.name) as circulation_count
		FROM `tabLibrary Book` lb
		LEFT JOIN `tabLibrary Category` lc ON lb.category = lc.name
		LEFT JOIN `tabLibrary Book Copy` lbc ON lb.name = lbc.book
		LEFT JOIN `tabLibrary Circulation` lcirc ON lbc.name = lcirc.book_copy 
			AND lcirc.docstatus = 1 
			AND lcirc.transaction_date >= %(from_date)s
		GROUP BY lb.category
		ORDER BY circulation_count DESC
	""", {"from_date": add_days(today(), -90)}, as_dict=True)
	
	return data
