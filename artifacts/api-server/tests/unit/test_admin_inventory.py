"""Public operation inventory is locked to the approved business operation list."""
from app.main import app


def test_all_draft_business_operations_are_registered():
    singles = [
        ("GET", "me"), ("GET", "menus"), ("GET", "permissions"), ("GET", "roles"),
        ("GET", "staff"), ("PUT", "staff/{admin_id}/roles"), ("GET", "dashboard"), ("GET", "analytics"),
        ("GET", "garage-owners"), ("GET", "garage-owners/{owner_id}"),
        ("GET", "garages"), ("GET", "garages/{garage_id}"), ("PATCH", "garages/{garage_id}/status"),
        ("PATCH", "garages/{garage_id}/verification"), ("GET", "garages/{garage_id}/reviews"),
        ("GET", "customers"), ("GET", "customers/{customer_id}"), ("GET", "customers/{customer_id}/vehicles"),
        ("GET", "customers/{customer_id}/reviews"), ("GET", "bookings"), ("GET", "bookings/{booking_id}"),
        ("GET", "bookings/exception-statistics"), ("GET", "jobs"), ("GET", "jobs/{job_id}"),
        ("GET", "jobs/{job_id}/timeline"), ("GET", "jobs/delays"), ("GET", "alerts"),
        ("GET", "finance/summary"), ("GET", "finance/trends"), ("GET", "invoices"),
        ("GET", "invoices/{invoice_id}"), ("GET", "payments"), ("GET", "payments/{payment_id}"),
        ("GET", "invoices/{invoice_id}/payment-attempts"), ("GET", "refunds"),
        ("GET", "disputes"), ("GET", "disputes/{dispute_id}"), ("GET", "notifications"),
        ("GET", "notifications/{notification_id}"), ("POST", "announcements/preview"),
        ("POST", "announcements"), ("GET", "announcements"), ("GET", "announcements/{announcement_id}"),
        ("GET", "announcements/{announcement_id}/deliveries"), ("GET", "support/tickets"),
        ("GET", "support/tickets/{ticket_id}"), ("PATCH", "support/tickets/{ticket_id}/assignment"),
        ("PATCH", "support/tickets/{ticket_id}/priority"), ("GET", "support/tickets/{ticket_id}/messages"),
        ("POST", "support/tickets/{ticket_id}/messages"), ("PATCH", "support/tickets/{ticket_id}/status"),
        ("GET", "garage-owner-statistics"), ("GET", "garage-owner-statistics/summary"),
        ("GET", "garage-owner-statistics/{owner_id}"), ("GET", "garage-owner-statistics/{owner_id}/trends"),
        ("POST", "reports/exports"), ("GET", "reports/exports/{export_id}"),
        ("GET", "reports/exports/{export_id}/download"), ("GET", "audit-logs"), ("GET", "audit-logs/{audit_id}"),
        ("GET", "activity"), ("GET", "activity/service-funnels/{booking_id}"),
    ]
    assert len(singles) == 62
    paths = app.openapi()["paths"]
    for method, path in singles:
        assert method.lower() in paths["/api/v1/admin/" + path]
