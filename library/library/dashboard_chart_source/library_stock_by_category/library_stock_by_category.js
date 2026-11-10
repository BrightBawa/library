frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Library Stock by Category"] = {
	method: "library.library.dashboard_chart_source.library_stock_by_category.library_stock_by_category.get",
	filters: [],
};
