// Copyright (c) 2025, GCIHS and contributors
// For license information, please see license.txt

frappe.ui.form.on('Library Settings', {
    sync_members_button: function (frm) {
        frappe.confirm(
            'This will sync all students and employees to library members. Continue?',
            function () {
                frappe.call({
                    method: 'library.library.doctype.library_settings.library_settings.sync_students_and_employees',
                    freeze: true,
                    freeze_message: __('Syncing members...'),
                    callback: function (r) {
                        if (r.message) {
                            frm.reload_doc();
                        }
                    }
                });
            }
        );
    }
});
