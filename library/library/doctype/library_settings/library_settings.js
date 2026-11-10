// Copyright (c) 2025, GCIHS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Library Settings", {
	sync_members_button(frm) {
		const dialog = new frappe.ui.Dialog({
			title: __("Sync Library Members"),
			fields: [
				{ fieldname: "students", fieldtype: "Check", label: __("Enabled Students"), default: 1 },
				{ fieldname: "employees", fieldtype: "Check", label: __("Active Employees"), default: 1 },
			],
			primary_action_label: __("Start"),
			primary_action(values) {
				const sources = [];
				if (values.students) sources.push("Student");
				if (values.employees) sources.push("Employee");
				if (!sources.length) return;
				dialog.hide();
				frappe.call({
					method: "library.library.doctype.library_settings.library_settings.sync_students_and_employees",
					args: { sources },
					callback() {
						frappe.show_alert({
							message: __("Sync started. You will get a message when it finishes."),
							indicator: "blue",
						});
					},
				});
			},
		});
		dialog.show();
	},
});
