"""Shared helpers for the library's script reports."""

import frappe


def date_conditions(filters, date_field, year_field=None):
	"""SQL conditions and values for from_date / to_date / academic_year filters."""
	conds, values = "", {}
	if filters.get("from_date"):
		conds += f" and {date_field} >= %(from_date)s"
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conds += f" and {date_field} <= %(to_date)s"
		values["to_date"] = filters.to_date
	if year_field and filters.get("academic_year"):
		conds += f" and {year_field} = %(academic_year)s"
		values["academic_year"] = filters.academic_year
	return conds, values


def has_returns():
	return bool(frappe.db.exists("DocType", "Library Issuance Return"))
