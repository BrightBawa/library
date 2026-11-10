"""A user whose only library role is Library Member sees only their own library records.

Their records are the Library Member rows whose ``user`` is them (filled from the Student's
or Employee's user) and the circulations, reservations, fines and issuances of those
members. Librarians, Library Managers, System Managers and Administrator are unrestricted.
"""

import frappe

STAFF_ROLES = {"Librarian", "Library Manager", "System Manager"}
READ_TYPES = {"read", "print", "email", "report", "export", None}


def _restricted(user):
	user = user or frappe.session.user
	if user == "Administrator":
		return False
	roles = set(frappe.get_roles(user))
	return "Library Member" in roles and not (roles & STAFF_ROLES)


def _own_members(user):
	return frappe.get_all("Library Member", filters={"user": user}, pluck="name")


def _member_condition(doctype, field, user):
	if not _restricted(user):
		return ""
	names = _own_members(user or frappe.session.user)
	if not names:
		return "1=0"
	values = ", ".join(frappe.db.escape(n) for n in names)
	return f"`tab{doctype}`.`{field}` in ({values})"


def library_member_query(user=None):
	return _member_condition("Library Member", "name", user)


def circulation_query(user=None):
	return _member_condition("Library Circulation", "member", user)


def reservation_query(user=None):
	return _member_condition("Library Reservation", "member", user)


def fine_query(user=None):
	return _member_condition("Library Fine", "member", user)


def issuance_query(user=None):
	return _member_condition("Library Book Issuance", "member", user)


def clearance_query(user=None):
	return _member_condition("Library Clearance", "member", user)


def has_member_permission(doc, ptype=None, user=None):
	"""Direct URLs and document API calls: a restricted user may only read their own records."""
	user = user or frappe.session.user
	if not _restricted(user):
		return True
	if ptype not in READ_TYPES:
		return False
	member = doc.name if doc.doctype == "Library Member" else doc.get("member")
	return member in _own_members(user)
