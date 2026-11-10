"""Install and migrate hooks. The workspace, number cards, charts, dashboard and reports are
standard module records under library/library/, imported by install and migrate."""

from library.library.notifications import ensure_email_templates


def after_install():
	ensure_email_templates()


def after_migrate():
	# Create-only: a template the library has edited is never overwritten.
	ensure_email_templates()
