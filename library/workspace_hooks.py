import frappe
from frappe import _


def workspace_before_save(doc, method):
    """Allow Library workspace to be tied to Library module but prevent auto-export"""
    if doc.name == "Library":
        # Set module to Library to tie workspace to the module
        if not doc.module:
            doc.module = "Library"
        # Set flag to skip export in on_update
        doc.flags.skip_export = True
