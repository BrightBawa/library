#!/usr/bin/env python3
"""Professional Library Workspace Setup"""

import frappe
import json


def create_workspace_shortcuts():
    """Create workspace shortcuts within the Library workspace"""
    
    # Get or create the Library workspace first
    if not frappe.db.exists('Workspace', 'Library'):
        doc = frappe.new_doc('Workspace')
        doc.name = 'Library'
        doc.label = 'Library'
        doc.title = 'Library'
        doc.icon = 'library'
        doc.indicator_color = 'blue'
        doc.module = None
        doc.public = 1
        doc.insert(ignore_permissions=True)
    
    workspace = frappe.get_doc('Workspace', 'Library')
    
    # Clear existing shortcuts
    workspace.shortcuts = []
    
    # Add shortcuts
    shortcuts = [
        {
            'label': 'New Library Book',
            'link_to': 'Library Book',
            'type': 'DocType',
            'icon': 'book',
            'color': 'blue',
            'format': '{} New'
        },
        {
            'label': 'New Library Member',
            'link_to': 'Library Member',
            'type': 'DocType',
            'icon': 'user',
            'color': 'green',
            'format': '{} New'
        },
        {
            'label': 'Issue Book',
            'link_to': 'Library Circulation',
            'type': 'DocType',
            'icon': 'book',
            'color': 'green',
            'format': '{} New'
        },
        {
            'label': 'Return Book',
            'link_to': 'Library Circulation',
            'type': 'DocType',
            'icon': 'return',
            'color': 'blue',
            'format': '{} Issued',
            'stats_filter': '{"transaction_type": "Issue"}'
        },
        {
            'label': 'Reservations',
            'link_to': 'Library Reservation',
            'type': 'DocType',
            'icon': 'calendar',
            'color': 'orange',
            'format': '{} Active'
        },
        {
            'label': 'Library Dashboard',
            'link_to': 'Library Dashboard',
            'type': 'Dashboard',
            'icon': 'dashboard',
            'color': 'purple'
        }
    ]
    
    for shortcut in shortcuts:
        workspace.append('shortcuts', shortcut)
    
    workspace.flags.ignore_validate = True
    workspace.flags.ignore_mandatory = True
    workspace.save(ignore_permissions=True)
    frappe.db.commit()
    print(f"  ✓ Added {len(shortcuts)} shortcuts to workspace")


def create_workspace_links():
    """Create workspace links (simplified - just ensure doctypes are accessible)"""
    workspace = frappe.get_doc('Workspace', 'Library')
    
    # Clear existing links
    workspace.links = []
    
    # Add all library doctypes as links
    all_links = [
        {'label': 'Library Book', 'link_to': 'Library Book', 'link_type': 'DocType', 'link_count': 0, 'onboard': 0},
        {'label': 'Library Category', 'link_to': 'Library Category', 'link_type': 'DocType', 'link_count': 0, 'onboard': 0},
        {'label': 'Library Book Copy', 'link_to': 'Library Book Copy', 'link_type': 'DocType', 'link_count': 0, 'onboard': 0},
        {'label': 'Library Circulation', 'link_to': 'Library Circulation', 'link_type': 'DocType', 'link_count': 0, 'onboard': 0},
        {'label': 'Library Member', 'link_to': 'Library Member', 'link_type': 'DocType', 'link_count': 0, 'onboard': 0},
        {'label': 'Library Reservation', 'link_to': 'Library Reservation', 'link_type': 'DocType', 'link_count': 0, 'onboard': 0},
        {'label': 'Library Fine', 'link_to': 'Library Fine', 'link_type': 'DocType', 'link_count': 0, 'onboard': 0},
        {'label': 'Library Settings', 'link_to': 'Library Settings', 'link_type': 'DocType', 'link_count': 0, 'onboard': 0},
        {'label': 'Library Membership Type', 'link_to': 'Library Membership Type', 'link_type': 'DocType', 'link_count': 0, 'onboard': 0},
    ]
    
    for link in all_links:
        workspace.append('links', link)
    
    workspace.flags.ignore_validate = True
    workspace.flags.ignore_mandatory = True
    workspace.save(ignore_permissions=True)
    frappe.db.commit()
    print(f"  ✓ Added {len(workspace.links)} workspace links")


def create_professional_workspace():
    """Create a comprehensive professional Library workspace"""
    
    # First, create the shortcuts
    create_workspace_shortcuts()
    
    # Create workspace links
    create_workspace_links()
    
    # Get the workspace
    workspace = frappe.get_doc('Workspace', 'Library')
    
    # Define professional workspace content
    content = [
        # Quick Actions Section
        {
            "id": "header_quick_actions",
            "type": "header",
            "data": {
                "text": "<span class='h4'><b>📚 Quick Actions</b></span>",
                "col": 12
            }
        },
        {
            "id": "shortcut_new_book",
            "type": "shortcut",
            "data": {
                "shortcut_name": "New Library Book",
                "col": 2
            }
        },
        {
            "id": "shortcut_new_member",
            "type": "shortcut",
            "data": {
                "shortcut_name": "New Library Member",
                "col": 2
            }
        },
        {
            "id": "shortcut_issue",
            "type": "shortcut",
            "data": {
                "shortcut_name": "Issue Book",
                "col": 2
            }
        },
        {
            "id": "shortcut_return",
            "type": "shortcut",
            "data": {
                "shortcut_name": "Return Book",
                "col": 2
            }
        },
        {
            "id": "shortcut_reserve",
            "type": "shortcut",
            "data": {
                "shortcut_name": "Reservations",
                "col": 2
            }
        },
        {
            "id": "shortcut_dash",
            "type": "shortcut",
            "data": {
                "shortcut_name": "Library Dashboard",
                "col": 2
            }
        },
        
        {"id": "spacer_1", "type": "spacer", "data": {"col": 12}},
        
        # Books & Inventory Section
        {
            "id": "header_books",
            "type": "header",
            "data": {
                "text": "<span class='h4'><b>📖 Books & Inventory</b></span>",
                "col": 12
            }
        },
        {
            "id": "card_total_books",
            "type": "number_card",
            "data": {
                "number_card_name": "Total Books",
                "col": 3
            }
        },
        {
            "id": "card_available",
            "type": "number_card",
            "data": {
                "number_card_name": "Available Books",
                "col": 3
            }
        },
        {
            "id": "card_issued",
            "type": "number_card",
            "data": {
                "number_card_name": "Issued Books",
                "col": 3
            }
        },
        {
            "id": "card_overdue",
            "type": "number_card",
            "data": {
                "number_card_name": "Overdue Books",
                "col": 3
            }
        },
        
        {"id": "spacer_2", "type": "spacer", "data": {"col": 12}},
        
        # Members & Activity Section
        {
            "id": "header_members",
            "type": "header",
            "data": {
                "text": "<span class='h4'><b>👥 Members & Activity</b></span>",
                "col": 12
            }
        },
        {
            "id": "card_total_members",
            "type": "number_card",
            "data": {
                "number_card_name": "Total Members",
                "col": 3
            }
        },
        {
            "id": "card_active_members",
            "type": "number_card",
            "data": {
                "number_card_name": "Active Members",
                "col": 3
            }
        },
        {
            "id": "card_reservations",
            "type": "number_card",
            "data": {
                "number_card_name": "Active Reservations",
                "col": 3
            }
        },
        {
            "id": "card_fines",
            "type": "number_card",
            "data": {
                "number_card_name": "Outstanding Fines",
                "col": 3
            }
        },
        
        {"id": "spacer_3", "type": "spacer", "data": {"col": 12}},
        
        # Analytics & Trends Section
        {
            "id": "header_analytics",
            "type": "header",
            "data": {
                "text": "<span class='h4'><b>📊 Analytics & Trends</b></span>",
                "col": 12
            }
        },
        {
            "id": "chart_circulation",
            "type": "chart",
            "data": {
                "chart_name": "Circulation Trend",
                "col": 6
            }
        },
        {
            "id": "chart_category",
            "type": "chart",
            "data": {
                "chart_name": "Category Distribution",
                "col": 6
            }
        },
        
        {
            "id": "chart_members",
            "type": "chart",
            "data": {
                "chart_name": "Member Activity",
                "col": 6
            }
        },
        {
            "id": "chart_fines",
            "type": "chart",
            "data": {
                "chart_name": "Fine Collection",
                "col": 6
            }
        },
        
        {"id": "spacer_5", "type": "spacer", "data": {"col": 12}},
        
        # Management Links Section
        {
            "id": "header_mgmt",
            "type": "header",
            "data": {
                "text": "<span class='h4'><b>⚙️ Management Links</b></span>",
                "col": 12
            }
        },
        {
            "id": "links_books_catalog",
            "type": "card",
            "data": {
                "card_name": "Books & Catalog",
                "col": 4
            },
            "links": [
                {"label": "Library Book", "link_to": "Library Book", "link_type": "DocType", "is_query_report": 0, "only_for": ""},
                {"label": "Library Category", "link_to": "Library Category", "link_type": "DocType", "is_query_report": 0, "only_for": ""},
                {"label": "Library Book Copy", "link_to": "Library Book Copy", "link_type": "DocType", "is_query_report": 0, "only_for": ""}
            ]
        },
        {
            "id": "links_circulation_members",
            "type": "card",
            "data": {
                "card_name": "Circulation & Members",
                "col": 4
            },
            "links": [
                {"label": "Library Circulation", "link_to": "Library Circulation", "link_type": "DocType", "is_query_report": 0, "only_for": ""},
                {"label": "Library Member", "link_to": "Library Member", "link_type": "DocType", "is_query_report": 0, "only_for": ""},
                {"label": "Library Reservation", "link_to": "Library Reservation", "link_type": "DocType", "is_query_report": 0, "only_for": ""},
                {"label": "Library Fine", "link_to": "Library Fine", "link_type": "DocType", "is_query_report": 0, "only_for": ""}
            ]
        },
        {
            "id": "links_reports_settings",
            "type": "card",
            "data": {
                "card_name": "Reports & Settings",
                "col": 4
            },
            "links": [
                {"label": "Library Settings", "link_to": "Library Settings", "link_type": "DocType", "is_query_report": 0, "only_for": ""},
                {"label": "Library Membership Type", "link_to": "Library Membership Type", "link_type": "DocType", "is_query_report": 0, "only_for": ""}
            ]
        }
    ]
    
    # Update workspace
    workspace.content = json.dumps(content)
    workspace.icon = 'library'
    workspace.indicator_color = 'blue'
    workspace.title = 'Library'
    workspace.public = 1
    workspace.module = 'Library'  # Tie to Library module
    workspace.flags.skip_export = True  # Prevent file export
    workspace.save(ignore_permissions=True)
    print('✓ Updated Library workspace with professional layout')
    
    frappe.db.commit()
    return True


def execute():
    """Main execution function"""
    print("\n=== Setting Up Professional Library Workspace ===\n")
    
    print("Step 1: Creating workspace shortcuts...")
    create_workspace_shortcuts()
    
    print("\nStep 2: Setting up workspace layout...")
    success = create_professional_workspace()
    
    if success:
        print("\n✓ Professional Library workspace setup completed!")
        print("\nWorkspace includes:")
        print("  • 6 Quick action shortcuts")
        print("  • 8 Number cards for key metrics")
        print("  • 4 Dashboard charts for analytics")
        print("  • 3 Link sections for navigation")
        print("  • Professional sectioned layout\n")
    
    return success


if __name__ == "__main__":
    execute()
