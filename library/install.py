import frappe
from frappe import _


def setup_library_workspace():
    """Setup Library workspace after installation"""
    try:
        # Reload module definition
        frappe.reload_doc('library', 'module_def', 'library')
        
        # Reload dashboards, charts, and cards
        frappe.reload_doc('library', 'dashboard', 'library_dashboard')
        
        # Reload number cards
        for card in ['total_books', 'available_books', 'issued_books', 'overdue_books',
                     'active_members', 'total_members', 'outstanding_fines', 'active_reservations']:
            frappe.reload_doc('library', 'number_card', card)
        
        # Reload dashboard charts
        for chart in ['circulation_trend', 'category_distribution', 'member_activity', 'fine_collection']:
            frappe.reload_doc('library', 'dashboard_chart', chart)
        
        # Create professional workspace
        from library.setup_professional_workspace import create_professional_workspace, create_workspace_shortcuts, create_workspace_links
        
        create_workspace_shortcuts()
        create_workspace_links()
        create_professional_workspace()
        
        frappe.db.commit()
        print("✓ Library workspace setup completed")
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Library Workspace Setup Error")
        print(f"Error setting up Library workspace: {str(e)}")
