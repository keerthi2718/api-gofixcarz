#!/usr/bin/env python3
"""Append concrete per-operation examples to the admin contract and rebuild its PDF."""

import json
import re
import textwrap
from pathlib import Path
from urllib.parse import urlencode

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
)


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
BASE = "https://api.gofixcarz.com"
MARKER = "<!-- GENERATED_ENDPOINT_EXAMPLES -->"
UUIDS = {
    "user_id": "11111111-1111-4111-8111-111111111111",
    "admin_id": "22222222-2222-4222-8222-222222222222",
    "garage_id": "33333333-3333-4333-8333-333333333333",
    "job_id": "44444444-4444-4444-8444-444444444444",
    "booking_id": "55555555-5555-4555-8555-555555555555",
    "owner_id": "66666666-6666-4666-8666-666666666666",
    "customer_id": "77777777-7777-4777-8777-777777777777",
    "ticket_id": "88888888-8888-4888-8888-888888888888",
    "invoice_id": "99999999-9999-4999-8999-999999999999",
    "payment_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "notification_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    "announcement_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    "export_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    "audit_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
    "dispute_id": "ffffffff-ffff-4fff-8fff-ffffffffffff",
    "message_id": "12121212-1212-4121-8121-121212121212",
    "preview_id": "13131313-1313-4131-8131-131313131313",
    "snapshot_id": "14141414-1414-4141-8141-141414141414",
}


def response(data, status=200, message="Success"):
    return {
        "success": True,
        "message": message,
        "data": data,
        "errors": [],
        "status_code": status,
    }


def source_record(kind, status, payload, amount_key=None, amount=None):
    row = {
        "id": UUIDS.get(kind.lower() + "_id", UUIDS["invoice_id"]),
        "kind": kind,
        "garage_id": UUIDS["garage_id"],
        "customer_id": UUIDS["customer_id"],
        "booking_id": UUIDS["booking_id"] if kind == "BOOKING_EVENT" else None,
        "job_id": UUIDS["job_id"] if kind in ("INVOICE", "PAYMENT") else None,
        "parent_id": UUIDS["invoice_id"] if kind in ("PAYMENT", "REFUND", "DISPUTE") else None,
        "status": status,
        "occurred_at": "2026-10-12T10:30:00Z",
        "version": 1,
        "currency": "INR" if kind in ("INVOICE", "PAYMENT", "REFUND") else None,
        **payload,
    }
    if amount_key:
        row[amount_key] = amount
    return row


USER = {
    "id": UUIDS["customer_id"],
    "first_name": "Aarav",
    "last_name": "Sharma",
    "name": "Aarav Sharma",
    "mobile": "9000000000",
    "country_code": "91",
    "country_code_2": None,
    "email": "aarav@example.test",
    "is_active": True,
    "account_status": "ACTIVE",
    "role": "GARAGE_OWNER",
    "created_at": "2026-01-10T09:00:00Z",
}
GARAGE = {
    "id": UUIDS["garage_id"],
    "user_id": UUIDS["owner_id"],
    "name": "Example Auto Care",
    "owner": "Aarav Sharma",
    "operational_status": "ACTIVE",
    "verification_status": "VERIFIED",
    "version": 3,
    "address": "12 Example Road",
    "city": "Pune",
    "state": "Maharashtra",
    "zipcode": "411001",
    "country": "IN",
    "alternate_number": None,
    "wheelers": ["2W", "4W"],
    "working_hours": {"monday": "09:00-18:00"},
    "latitude": 18.5204,
    "longitude": 73.8567,
    "logo_object_key": None,
    "logo_url": None,
    "created_at": "2026-01-10T09:00:00Z",
    "updated_at": "2026-10-12T10:00:00Z",
}
JOB = {
    "id": UUIDS["job_id"],
    "job_number": "J-2026-0042",
    "garage_id": UUIDS["garage_id"],
    "customer_id": UUIDS["customer_id"],
    "vehicle_id": "15151515-1515-4151-8151-151515151515",
    "booking_id": UUIDS["booking_id"],
    "customer_name": "Aarav Sharma",
    "customer_mobile": "9000000000",
    "registration_number": "MH12AB1234",
    "brand": "Maruti Suzuki",
    "vehicle_model": "Swift",
    "fuel_type": "PETROL",
    "odometer_km": 42000,
    "photos": [],
    "inspection": {"findings": "Brake pads worn", "parts_needed": ["Brake pads"]},
    "services": [{"name": "Brake pad replacement", "price": "2500.00", "qty": 1}],
    "labour": {"description": "Front brake service", "charge": "800.00"},
    "billing": {
        "services_total": "2500.00",
        "labour_total": "800.00",
        "subtotal": "3300.00",
        "gst_amount": "594.00",
        "grand_total": "3894.00",
    },
    "status": "IN_PROGRESS",
    "description": "Front brake service",
    "estimated_amount": "3894.00",
    "final_amount": None,
    "completed_at": None,
    "created_at": "2026-10-10T09:00:00Z",
    "updated_at": "2026-10-12T10:00:00Z",
}
BOOKING = {
    "id": UUIDS["booking_id"],
    "garage_id": UUIDS["garage_id"],
    "customer_id": UUIDS["customer_id"],
    "vehicle_id": "15151515-1515-4151-8151-151515151515",
    "status": "ACCEPTED",
    "booking_date": "2026-10-15",
    "notes": "Please check the brakes",
    "customer_name": "Aarav Sharma",
    "customer_mobile": "9000000000",
    "service_requested": "Brake service",
    "created_at": "2026-10-10T08:00:00Z",
    "updated_at": "2026-10-10T08:30:00Z",
}


def typed_data_examples():
    timeline = {
        "id": UUIDS["message_id"],
        "job_id": UUIDS["job_id"],
        "status": "IN_PROGRESS",
        "notes": "Inspection started",
        "created_at": "2026-10-12T10:00:00Z",
    }
    audit = {
        "id": UUIDS["audit_id"],
        "actor_id": UUIDS["admin_id"],
        "admin_account_id": UUIDS["admin_id"],
        "action": "jobs.read",
        "resource_id": UUIDS["job_id"],
        "details": {"source": "admin_console"},
        "created_at": "2026-10-12T10:30:00Z",
    }
    activity_event = {
        "id": "event-20261012-001",
        "event_type": "JOB_CREATED",
        "customer_id": UUIDS["customer_id"],
        "owner_id": UUIDS["owner_id"],
        "garage_id": UUIDS["garage_id"],
        "booking_id": UUIDS["booking_id"],
        "job_id": UUIDS["job_id"],
        "timestamp": "2026-10-12T10:00:00Z",
        "status": "IN_PROGRESS",
        "source": "job.created_at",
    }
    owner = {
        **USER,
        "id": UUIDS["owner_id"],
        "role": "GARAGE_OWNER",
        "display_name": "Aarav Sharma",
        "garage_ids": [UUIDS["garage_id"]],
        "total_garages": 1,
        "related_garages_truncated": False,
        "cities": ["Pune"],
        "bookings": 3,
        "jobs_created": 4,
        "completed_jobs": 2,
        "completed_job_amount_paise": 389400,
        "currency": "INR",
        "average_rating": 4.5,
    }
    return {
        "AdminAuditResponse": audit,
        "AdminTimelineEvent": timeline,
        "AdminActivityEvent": activity_event,
        "AdminOwnerSummary": owner,
        "AdminOwnerDetail": {**owner, "garages": [GARAGE]},
        "AdminBookingDetail": {
            **BOOKING,
            "customer": None,
            "vehicle": None,
            "linked_job_ids": [UUIDS["job_id"]],
            "linked_jobs_truncated": False,
            "decision_actor": UUIDS["owner_id"],
            "decision_reason": "Appointment confirmed",
            "decision_timestamp": "2026-10-10T08:30:00Z",
            "missing_history": [],
            "history": [],
            "history_truncated": False,
        },
        "AdminFunnelResponse": {
            "booking_id": UUIDS["booking_id"],
            "customer_id": UUIDS["customer_id"],
            "garage_id": UUIDS["garage_id"],
            "job_ids": [UUIDS["job_id"]],
            "linked_jobs_truncated": False,
            "events": {
                "items": [activity_event],
                "total": 1,
                "page": 1,
                "page_size": 20,
                "pages": 1,
            },
            "data_coverage": {
                "booking_decisions": True,
                "invoices": False,
                "payments": False,
                "reviews": False,
            },
        },
        "AdminActivityPage": {
            "items": [activity_event],
            "total": 1,
            "page": 1,
            "page_size": 20,
            "pages": 1,
            "filters": {"timezone": "UTC", "date_from": "2026-10-01", "date_to": "2026-10-12"},
            "generated_at": "2026-10-12T11:00:00Z",
            "unavailable_history": ["payments", "reviews"],
            "restricted_history": [],
        },
        "AdminOwnerPage": {
            "items": [owner],
            "total": 1,
            "page": 1,
            "page_size": 20,
            "pages": 1,
            "filters": {"timezone": "UTC", "date_from": "2026-10-01", "date_to": "2026-10-12"},
            "generated_at": "2026-10-12T11:00:00Z",
            "metric_bases": {
                "bookings": "booking.created_at",
                "jobs_created": "job.created_at",
                "completed_jobs": "current COMPLETED state within job.created_at cohort",
                "completed_job_amount_paise": "job.completed_at; recorded final amounts, not captured payments",
            },
            "unavailable_data_sources": ["reviews", "payment_collections"],
        },
        "AdminOwnerDetailResponse": {
            **owner,
            "garages": [GARAGE],
            "filters": {"timezone": "UTC", "date_from": "2026-10-01", "date_to": "2026-10-12"},
            "generated_at": "2026-10-12T11:00:00Z",
            "metric_bases": {
                "bookings": "booking.created_at",
                "jobs_created": "job.created_at",
                "completed_jobs": "current COMPLETED state within job.created_at cohort",
                "completed_job_amount_paise": "job.completed_at; recorded final amounts, not captured payments",
            },
            "unavailable_data_sources": ["reviews", "payment_collections"],
        },
    }


def generic_data(method, path):
    """Representative outputs for routes whose OpenAPI response data is intentionally generic."""
    paged = lambda item: {
        "items": [item],
        "total": 1,
        "page": 1,
        "page_size": 20,
        "pages": 1,
    }
    review = source_record(
        "REVIEW", "PUBLISHED", {"rating": 5, "text": "Clear estimate and prompt service"}
    )
    ticket = source_record(
        "TICKET", "IN_PROGRESS",
        {"subject": "Brake service question", "description": "Please share an update.", "priority": "HIGH",
         "assignee_id": UUIDS["admin_id"]},
    )
    invoice = source_record(
        "INVOICE", "PAID", {"invoice_number": "INV-2026-0042", "subtotal": 330000,
         "tax_amount": 59400, "discount_amount": 0}, "total_amount", 389400,
    )
    payment = source_record(
        "PAYMENT", "CAPTURED", {"gateway_reference": "pay_demo_0042"}, "amount", 389400,
    )
    notification = {
        "id": UUIDS["notification_id"], "garage_id": UUIDS["garage_id"],
        "title": "Job status updated", "message": "Your vehicle is in progress.",
        "channel": "IN_APP", "status": "DELIVERED", "read_at": None,
    }
    announcement = {
        "id": UUIDS["announcement_id"], "status": "DELIVERED",
        "title": "Service update", "message": "New operating hours start Monday.",
        "delivery_count": 1, "created_at": "2026-10-12T10:30:00Z",
    }
    customer = {
        "id": UUIDS["customer_id"], "name": "Aarav Sharma", "email": "aarav@example.test",
        "mobile": "9000000000", "account_status": "ACTIVE", "last_activity_at": "2026-10-12T09:00:00Z",
        "garage_ids": [UUIDS["garage_id"]], "has_support_flags": True,
        "has_failed_payments": False, "source": "CUSTOMER_APP", "restricted_fields": [],
    }
    if path.endswith("/admin-auth/sign-in") or path.endswith("/admin-auth/mfa") or path.endswith("/admin-auth/refresh"):
        return {
            "access_token": "<access-token-from-response>",
            "refresh_token": "<refresh-token-from-response>",
            "token_type": "bearer",
            "expires_in": 900,
            "user": {
                "id": UUIDS["admin_id"], "email": "admin@example.test", "name": "Example Admin",
                "role": "ADMIN", "is_active": True, "role_ids": ["role_operations"],
                "permissions": ["garages.read", "jobs.read", "support.read"],
                "data_scope": {"type": "PLATFORM", "garage_ids": []},
            },
        }
    if path.endswith("/admin-auth/logout"):
        return {"logged_out": True}
    if path.endswith("/admin/menus"):
        return {"menus": [
            {"key": "dashboard", "label": "Dashboard", "api": "/api/v1/admin/dashboard"},
            {"key": "jobs", "label": "Jobs", "api": "/api/v1/admin/jobs"},
            {"key": "support", "label": "Support", "api": "/api/v1/admin/support/tickets"},
        ]}
    if path.endswith("/admin/me"):
        return {
            "id": UUIDS["admin_id"], "email": "admin@example.test", "name": "Example Admin",
            "role": "ADMIN", "is_active": True, "permissions": ["garages.read", "jobs.read"],
            "role_ids": ["role_operations"],
            "data_scope": {"type": "PLATFORM", "garage_ids": []},
        }
    if path.endswith("/admin/dashboard"):
        return {
            "total_users": 320, "active_users": 286, "total_garages": 42,
            "total_jobs": 790, "jobs_today": 12,
            "status_counts": {"OPEN": 8, "IN_PROGRESS": 24, "WAITING_FOR_PARTS": 5,
                              "QUALITY_CHECK": 3, "READY": 2, "COMPLETED": 740, "CANCELLED": 8},
            "total_bookings": 510, "pending_bookings": 14,
            "revenue_today": "12500.00", "revenue_this_month": "184250.00",
            "total_revenue": "2450000.00", "billing_issue_count": 3,
            "snapshot_id": UUIDS["snapshot_id"], "generated_at": "2026-10-12T11:00:00Z",
            "extended_metrics": {
                "gross_collected_amount": 389400, "refunded_amount": 0,
                "net_collected_amount": 389400, "captured_payments": 1,
                "failed_attempts": 0, "paid_invoice_count": 1,
                "issued_invoice_count": 1, "issued_invoice_total_amount": 389400,
                "average_invoice_amount": 389400, "currency": "INR", "money_unit": "paise",
                "source_status": "RECORDED_EVENTS", "snapshot_expires_at": "2026-10-12T17:00:00Z",
            },
        }
    if path.endswith("/admin/analytics"):
        return {
            "garage_id": UUIDS["garage_id"], "period": "monthly",
            "start_date": "2026-01-01", "end_date": "2026-10-12",
            "total_jobs": 4, "total_revenue": "7788.00",
            "status_counts": {"OPEN": 0, "IN_PROGRESS": 1, "WAITING_FOR_PARTS": 0,
                              "QUALITY_CHECK": 0, "READY": 0, "COMPLETED": 3, "CANCELLED": 0},
            "graph_data": [{"label": "Oct 2026", "job_count": 4, "completed_count": 3, "revenue": "7788.00"}],
            "snapshot_id": UUIDS["snapshot_id"], "generated_at": "2026-10-12T11:00:00Z",
        }
    if path.endswith("/finance/summary"):
        return {
            "snapshot_id": UUIDS["snapshot_id"], "generated_at": "2026-10-12T11:00:00Z",
            "expires_at": "2026-10-12T17:00:00Z",
            "filters": {"date_from": "2026-09-13", "date_to": "2026-10-12", "timezone": "UTC"},
            "metric_definitions": {"collections": "CAPTURED payment events; amounts in integer INR paise"},
            "gross_collected_amount": 389400, "refunded_amount": 0,
            "net_collected_amount": 389400, "captured_payments": 1, "failed_attempts": 0,
            "paid_invoice_count": 1, "issued_invoice_count": 1,
            "issued_invoice_total_amount": 389400, "average_invoice_amount": 389400,
            "currency": "INR", "money_unit": "paise", "source_status": "RECORDED_EVENTS",
        }
    if path.endswith("/finance/trends") or path.endswith("/trends"):
        result = {
            "snapshot_id": UUIDS["snapshot_id"], "generated_at": "2026-10-12T11:00:00Z",
            "expires_at": "2026-10-12T17:00:00Z",
            "filters": {"date_from": "2026-10-01", "date_to": "2026-10-12", "timezone": "UTC"},
            "metric_definitions": {"collections": "CAPTURED payment events; amounts in integer INR paise"},
            "period": "daily",
            "series": [{"date": "2026-10-12", "jobs_created": 1, "jobs_completed": 1,
                        "gross_collected_amount": 389400, "refunded_amount": 0,
                        "net_collected_amount": 389400}],
        }
        if "/garage-owner-statistics/" in path:
            result["owner_id"] = UUIDS["owner_id"]
        return result
    if path.endswith("/garage-owner-statistics/summary"):
        return {
            "snapshot_id": UUIDS["snapshot_id"], "generated_at": "2026-10-12T11:00:00Z",
            "expires_at": "2026-10-12T17:00:00Z", "exclude_inactive": False,
            "filters": {"date_from": "2026-09-13", "date_to": "2026-10-12", "timezone": "UTC"},
            "metric_definitions": {"jobs": "created-in-window cohort; current status frozen at generated_at"},
            "jobs_created": 4, "eligible_garages": 1, "eligible_accepted_bookings": 3,
            "converted_bookings": 2, "completion_sample_size": 2, "completion_total_hours": 24.0,
            "completion_exclusions": 0, "gross_collected_amount": 389400, "refunded_amount": 0,
            "net_collected_amount": 389400, "paid_invoice_count": 1, "issued_invoice_count": 1,
            "issued_invoice_total_amount": 389400, "failed_attempts": 0,
            "status_counts": {"OPEN": 0, "IN_PROGRESS": 1, "WAITING_FOR_PARTS": 0,
                              "QUALITY_CHECK": 0, "READY": 0, "COMPLETED": 3, "CANCELLED": 0},
            "average_jobs_per_garage": 4.0, "conversion_percent": 66.67,
            "average_completion_hours": 12.0, "average_invoice_amount": 389400,
        }
    if path.endswith("/garage-owner-statistics") and method == "GET":
        row = {
            "owner_id": UUIDS["owner_id"], "owner_name": "Aarav Sharma",
            "garage_ids": [UUIDS["garage_id"]], "jobs_created": 4,
            "status_counts": {"OPEN": 0, "IN_PROGRESS": 1, "WAITING_FOR_PARTS": 0,
                              "QUALITY_CHECK": 0, "READY": 0, "COMPLETED": 3, "CANCELLED": 0},
            "completed_jobs": 3, "eligible_garages": 1, "average_jobs_per_garage": 4.0,
            "eligible_accepted_bookings": 3, "converted_bookings": 2, "conversion_percent": 66.67,
            "completion_sample_size": 2, "completion_total_hours": 24.0,
            "average_completion_hours": 12.0, "completion_exclusions": 0,
            "garage_breakdown": [{"garage_id": UUIDS["garage_id"], "jobs_created": 4}],
            "gross_collected_amount": 389400, "refunded_amount": 0,
            "net_collected_amount": 389400, "captured_payments": 1, "failed_attempts": 0,
            "paid_invoice_count": 1, "issued_invoice_count": 1,
            "issued_invoice_total_amount": 389400, "average_invoice_amount": 389400,
            "currency": "INR", "money_unit": "paise", "source_status": "RECORDED_EVENTS",
            "missing_sources": [], "rank": 1,
        }
        return {
            "snapshot_id": UUIDS["snapshot_id"], "generated_at": "2026-10-12T11:00:00Z",
            "expires_at": "2026-10-12T17:00:00Z",
            "filters": {"date_from": "2026-09-13", "date_to": "2026-10-12", "timezone": "UTC"},
            "metric_definitions": {"jobs": "created-in-window cohort; current status frozen at generated_at"},
            "items": [row], "total": 1, "page": 1, "page_size": 20,
            "source_totals": {
                "jobs_created": 4, "eligible_garages": 1, "eligible_accepted_bookings": 3,
                "converted_bookings": 2, "completion_sample_size": 2,
                "completion_total_hours": 24.0, "completion_exclusions": 0,
                "gross_collected_amount": 389400, "refunded_amount": 0,
                "net_collected_amount": 389400, "paid_invoice_count": 1,
                "issued_invoice_count": 1, "issued_invoice_total_amount": 389400,
                "failed_attempts": 0,
                "status_counts": {"OPEN": 0, "IN_PROGRESS": 1, "WAITING_FOR_PARTS": 0,
                                  "QUALITY_CHECK": 0, "READY": 0, "COMPLETED": 3, "CANCELLED": 0},
                "average_jobs_per_garage": 4.0, "conversion_percent": 66.67,
                "average_completion_hours": 12.0, "average_invoice_amount": 389400,
            },
        }
    if "/garage-owner-statistics/" in path:
        return {
            "snapshot_id": UUIDS["snapshot_id"], "generated_at": "2026-10-12T11:00:00Z",
            "expires_at": "2026-10-12T17:00:00Z",
            "filters": {"date_from": "2026-09-13", "date_to": "2026-10-12", "timezone": "UTC"},
            "metric_definitions": {"jobs": "created-in-window cohort; current status frozen at generated_at"},
            "owner_id": UUIDS["owner_id"], "owner_name": "Aarav Sharma",
            "garage_ids": [UUIDS["garage_id"]], "jobs_created": 4,
            "status_counts": {"OPEN": 0, "IN_PROGRESS": 1, "WAITING_FOR_PARTS": 0,
                              "QUALITY_CHECK": 0, "READY": 0, "COMPLETED": 3, "CANCELLED": 0},
            "completed_jobs": 3, "eligible_garages": 1, "average_jobs_per_garage": 4.0,
            "eligible_accepted_bookings": 3, "converted_bookings": 2, "conversion_percent": 66.67,
            "completion_sample_size": 2, "completion_total_hours": 24.0,
            "average_completion_hours": 12.0, "completion_exclusions": 0,
            "garage_breakdown": [{"garage_id": UUIDS["garage_id"], "jobs_created": 4}],
            "gross_collected_amount": 389400, "refunded_amount": 0,
            "net_collected_amount": 389400, "captured_payments": 1, "failed_attempts": 0,
            "paid_invoice_count": 1, "issued_invoice_count": 1,
            "issued_invoice_total_amount": 389400, "average_invoice_amount": 389400,
            "currency": "INR", "money_unit": "paise", "source_status": "RECORDED_EVENTS",
            "missing_sources": [],
        }
    if path.endswith("/bookings/exception-statistics"):
        return {
            "filters": {"date_from": "2026-10-01", "date_to": "2026-10-12", "timezone": "UTC"},
            "generated_at": "2026-10-12T11:00:00Z",
            "cohort": "booking.created_at", "rejected": 1, "cancelled": 0, "expired": 0,
            "reason_counts": {"UNSPECIFIED": 1},
            "breakdown": [{"owner_id": UUIDS["owner_id"], "city": "Pune", "reason": "UNSPECIFIED", "count": 1}],
            "breakdown_truncated": False, "unavailable_states": ["CANCELLED", "EXPIRED"],
            "reason_history_available": False,
        }
    if path.endswith("/garages/{garage_id}/status") or path.endswith("/garages/{garage_id}/verification"):
        return {"id": UUIDS["garage_id"], "operational_status": "ACTIVE",
                "verification_status": "VERIFIED", "version": 4, "new_work_allowed": True}
    if path.endswith("/garages/{garage_id}/reviews"):
        return paged(review)
    if path.endswith("/customers"):
        return {**paged(customer)}
    if path.endswith("/customers/{customer_id}"):
        return {
            **customer, "vehicles": [{
                "id": "15151515-1515-4151-8151-151515151515",
                "kind": "VEHICLE", "garage_id": UUIDS["garage_id"],
                "customer_id": UUIDS["customer_id"], "booking_id": None,
                "job_id": None, "parent_id": None, "status": "ACTIVE",
                "occurred_at": "2026-10-12T09:00:00Z", "version": 1, "currency": None,
                "registration_number": "MH12AB1234", "brand": "Maruti Suzuki",
                "model": "Swift", "fuel_type": "PETROL", "customer_id": UUIDS["customer_id"],
            }],
            "reviews": [review], "preview_limit": 20,
        }
    if path.endswith("/customers/{customer_id}/vehicles"):
        return paged({
            "id": "15151515-1515-4151-8151-151515151515",
            "kind": "VEHICLE", "garage_id": UUIDS["garage_id"],
            "customer_id": UUIDS["customer_id"], "booking_id": None,
            "job_id": None, "parent_id": None, "status": "ACTIVE",
            "occurred_at": "2026-10-12T09:00:00Z", "version": 1, "currency": None,
            "registration_number": "MH12AB1234", "brand": "Maruti Suzuki",
            "model": "Swift", "fuel_type": "PETROL",
        })
    if path.endswith("/customers/{customer_id}/reviews"):
        return paged(review)
    if path.endswith("/jobs/delays"):
        return {"items": [{
            "job_id": UUIDS["job_id"], "job_number": "J-2026-0042", "garage_id": UUIDS["garage_id"],
            "status": "IN_PROGRESS", "state_entered_at": "2026-10-12T08:00:00Z",
            "state_age_hours": 3.5, "threshold_hours": 2, "overdue": True,
            "as_of": "2026-10-12T11:30:00Z",
            "duration_basis": "latest recorded entry to current state; creation fallback",
        }], "total": 1, "page": 1, "page_size": 20, "as_of": "2026-10-12T11:30:00Z"}
    if path.endswith("/alerts"):
        return {"items": [{
            "id": "a7be53b0-3b94-5535-8c04-1504267b8f7c", "type": "JOB_DELAY",
            "severity": "HIGH", "job_id": UUIDS["job_id"], "job_number": "J-2026-0042",
            "garage_id": UUIDS["garage_id"], "status": "IN_PROGRESS",
            "state_entered_at": "2026-10-12T07:00:00Z", "state_age_hours": 4.5,
            "threshold_hours": 2, "overdue": True, "as_of": "2026-10-12T11:30:00Z",
            "duration_basis": "latest recorded entry to current state; creation fallback",
        }], "total": 1, "page": 1, "page_size": 20,
            "as_of": "2026-10-12T11:30:00Z", "generation": "live deterministic state episodes"}
    if path.endswith("/notifications"):
        return paged(notification)
    if path.endswith("/notifications/{notification_id}"):
        return {**notification, "created_at": "2026-10-12T10:30:00Z", "attempts": []}
    if path.endswith("/announcements/preview"):
        return {"preview_id": UUIDS["preview_id"], "recipient_count": 1, "delivery_count": 1,
                "channels": ["IN_APP"], "expires_at": "2026-10-12T11:05:00Z"}
    if path.endswith("/announcements") and method == "POST":
        return announcement
    if path.endswith("/announcements") and method == "GET":
        return paged(announcement)
    if path.endswith("/announcements/{announcement_id}"):
        return announcement
    if path.endswith("/announcements/{announcement_id}/deliveries"):
        return {"items": [{"garage_id": UUIDS["garage_id"], "recipient_id": UUIDS["owner_id"],
                           "channel": "IN_APP", "status": "DELIVERED"}],
                "total": 1, "page": 1, "page_size": 20}
    if path.endswith("/invoices"):
        return {**paged(invoice), "filters": {"timezone": "UTC"}, "money_unit": "paise",
                "currency": "INR", "source_status": "RECORDED_EVENTS"}
    if path.endswith("/invoices/{invoice_id}"):
        return {**invoice, "linked_records": [payment], "preview_limit": 20}
    if path.endswith("/invoices/{invoice_id}/payment-attempts"):
        return paged(payment)
    if path.endswith("/payments"):
        return {**paged(payment), "filters": {"timezone": "UTC"}, "money_unit": "paise",
                "currency": "INR", "source_status": "RECORDED_EVENTS"}
    if path.endswith("/payments/{payment_id}"):
        return {**payment, "linked_records": [], "preview_limit": 20}
    if path.endswith("/refunds"):
        refund = source_record("REFUND", "SETTLED", {"reason": "Customer request"}, "amount", 0)
        refund["parent_id"] = UUIDS["payment_id"]
        return {**paged(refund), "filters": {"timezone": "UTC"}, "money_unit": "paise",
                "currency": "INR", "source_status": "RECORDED_EVENTS"}
    if path.endswith("/disputes"):
        dispute = source_record("DISPUTE", "OPEN", {"reason": "Payment not recognized"}, "amount", None)
        return {**paged(dispute), "filters": {"timezone": "UTC"}, "money_unit": "paise",
                "currency": "INR", "source_status": "RECORDED_EVENTS"}
    if path.endswith("/disputes/{dispute_id}"):
        return source_record("DISPUTE", "OPEN", {"reason": "Payment not recognized"}, "amount", None)
    if path.endswith("/permissions"):
        return {"items": [{"code": "jobs.read", "description": "jobs read"},
                          {"code": "support.reply", "description": "support reply"}]}
    if path.endswith("/roles"):
        return {"items": [{"id": "role_support", "name": "Support",
                           "permissions": ["support.read", "support.reply"]}]}
    if path.endswith("/staff"):
        return {
            "items": [{
                "id": UUIDS["admin_id"], "display_name": "Example Admin",
                "email": "admin@example.test", "is_active": True,
                "role_ids": ["role_support"], "permissions": ["support.read", "support.reply"],
                "data_scope": {"type": "PLATFORM", "garage_ids": []},
                "mfa_enrolled": True, "mfa_required": False,
            }],
            "total": 1, "page": 1, "page_size": 20, "pages": 1,
        }
    if path.endswith("/staff/{admin_id}/roles"):
        return {
            "id": UUIDS["admin_id"], "display_name": "Example Admin",
            "email": "admin@example.test", "is_active": True,
            "role_ids": ["role_support"], "permissions": ["support.read", "support.reply"],
            "data_scope": {"type": "PLATFORM", "garage_ids": []},
            "mfa_enrolled": True, "mfa_required": False,
        }
    if path.endswith("/reports/exports") and method == "POST":
        return {
            "report_type": "OPERATIONS", "format": "CSV",
            "filters": {"date_from": "2026-10-01", "date_to": "2026-10-12", "timezone": "UTC"},
            "snapshot_id": UUIDS["snapshot_id"], "generated_at": "2026-10-12T11:00:00Z",
            "row_count": 13, "source_totals": {"jobs_created": 4, "bookings_created": 9},
            "metric_definitions": {"jobs": "created-in-window cohort"},
            "id": UUIDS["export_id"], "status": "QUEUED", "expires_at": "2026-10-13T11:00:00Z",
            "error": None, "download_path": None,
        }
    if path.endswith("/reports/exports/{export_id}"):
        return {
            "report_type": "OPERATIONS", "format": "CSV",
            "filters": {"date_from": "2026-10-01", "date_to": "2026-10-12", "timezone": "UTC"},
            "snapshot_id": UUIDS["snapshot_id"], "generated_at": "2026-10-12T11:00:00Z",
            "row_count": 13, "source_totals": {"jobs_created": 4, "bookings_created": 9},
            "metric_definitions": {"jobs": "created-in-window cohort"},
            "id": UUIDS["export_id"], "status": "READY", "expires_at": "2026-10-13T11:00:00Z",
            "error": None, "download_path": f"/api/v1/admin/reports/exports/{UUIDS['export_id']}/download",
        }
    if path.endswith("/support/tickets") and method == "GET":
        return paged(ticket)
    if path.endswith("/support/tickets/{ticket_id}") and method == "GET":
        return ticket
    if path.endswith("/support/tickets/{ticket_id}/assignment"):
        return {**ticket, "version": 3}
    if path.endswith("/support/tickets/{ticket_id}/priority"):
        return {**ticket, "version": 3, "priority": "HIGH"}
    if path.endswith("/support/tickets/{ticket_id}/status"):
        return {**ticket, "version": 3, "status": "RESOLVED", "resolution": "Replacement part installed"}
    if path.endswith("/support/tickets/{ticket_id}/messages") and method == "GET":
        return {"items": [{
            "id": UUIDS["message_id"], "sender_role": "ADMIN",
            "text": "The garage has confirmed the appointment.", "created_at": "2026-10-12T10:30:00Z",
            "client_message_id": "support-reply-demo-001",
        }], "next_cursor": None}
    if path.endswith("/support/tickets/{ticket_id}/messages") and method == "POST":
        return {
            "id": UUIDS["message_id"], "sender_role": "ADMIN",
            "text": "The garage has confirmed the appointment.", "created_at": "2026-10-12T10:30:00Z",
            "client_message_id": "support-reply-demo-001",
        }
    if path.endswith("/users/{user_id}/status"):
        return {**USER, "is_active": False, "account_status": "INACTIVE"}
    raise ValueError(f"No concrete generic response example for {method.upper()} {path}")


def merge_all_of(schema):
    merged = dict(schema)
    props = dict(schema.get("properties", {}))
    required = set(schema.get("required", []))
    for part in schema.get("allOf", []):
        if "properties" in part:
            props.update(part["properties"])
            required.update(part.get("required", []))
    if props:
        merged["properties"] = props
    if required:
        merged["required"] = list(required)
    return merged


def sample_from_schema(schema, components, prop_name="", depth=0):
    if depth > 14:
        return None
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        target = merge_all_of(components.get(name, {}))
        return sample_from_schema(target, components, prop_name or name, depth + 1)
    schema = merge_all_of(schema)
    for key in ("anyOf", "oneOf"):
        if key in schema:
            choices = [x for x in schema[key] if x.get("type") != "null"]
            return sample_from_schema(choices[0] if choices else schema[key][0], components, prop_name, depth + 1)
    if "enum" in schema:
        return schema["enum"][0]
    typ = schema.get("type")
    if isinstance(typ, list):
        typ = next((x for x in typ if x != "null"), "string")
    if typ == "array":
        item_schema = schema.get("items", {})
        name = prop_name.lower()
        if name in ("garage_ids", "role_ids", "photos", "timelines", "history", "errors"):
            return []
        return [sample_from_schema(item_schema, components, prop_name, depth + 1)]
    if typ == "object" or "properties" in schema:
        props = schema.get("properties", {})
        result = {}
        for key, value in props.items():
            result[key] = sample_from_schema(value, components, key, depth + 1)
        if not props and isinstance(schema.get("additionalProperties"), dict):
            result["example"] = sample_from_schema(schema["additionalProperties"], components, "example", depth + 1)
        return result
    fmt = schema.get("format")
    name = prop_name.lower()
    if fmt == "uuid" or name.endswith("_id") or name == "id":
        return UUIDS.get(name, UUIDS["user_id"])
    if fmt == "date-time" or name.endswith("_at") or name in ("generated_at", "timestamp"):
        return "2026-10-12T10:30:00Z"
    if fmt == "date" or name.endswith("_date") or name in ("date_from", "date_to", "start_date", "end_date"):
        return "2026-10-12"
    if fmt == "email" or name == "email":
        return "admin@example.test" if "admin" in prop_name.lower() else "aarav@example.test"
    if typ == "boolean":
        return True
    if typ == "integer":
        if name in ("page", "page_size", "pages", "total", "count", "rank", "version"):
            return 1 if name != "page_size" else 20
        return 0
    if typ == "number":
        return 4.5 if "rating" in name else 0.0
    if typ == "string":
        overrides = {
            "name": "Example Auto Care",
            "display_name": "Aarav Sharma",
            "first_name": "Aarav",
            "last_name": "Sharma",
            "mobile": "9000000000",
            "country_code": "91",
            "city": "Pune",
            "state": "Maharashtra",
            "zipcode": "411001",
            "currency": "INR",
            "message": "Example response message",
            "text": "Example response text",
            "description": "Example description",
            "title": "Example title",
            "notes": "Example notes",
            "status": "ACTIVE",
            "role": "GARAGE_OWNER",
        }
        if name in overrides:
            return overrides[name]
        return "<example>"
    return None


def resolve_data_schema(operation, components):
    for code in ("200", "201", "202"):
        response_obj = operation.get("responses", {}).get(code, {})
        schema = response_obj.get("content", {}).get("application/json", {}).get("schema")
        if not schema:
            continue
        if "$ref" in schema:
            wrapper = components.get(schema["$ref"].rsplit("/", 1)[-1], {})
            data_schema = wrapper.get("properties", {}).get("data", {})
            choices = data_schema.get("anyOf", [])
            data_schema = next((x for x in choices if x.get("type") != "null"), data_schema)
            return code, data_schema
        return code, schema
    return "200", {}


def sample_path_value(name):
    return UUIDS.get(name, UUIDS.get(name.removesuffix("_id") + "_id", UUIDS["user_id"]))


def sample_param(parameter, components, path):
    schema = parameter.get("schema", {})
    while True:
        if "$ref" in schema:
            schema = components.get(schema["$ref"].rsplit("/", 1)[-1], {})
        elif "anyOf" in schema or "oneOf" in schema:
            key = "anyOf" if "anyOf" in schema else "oneOf"
            schema = next((x for x in schema[key] if x.get("type") != "null"), schema[key][0])
        else:
            break
    if "default" in schema:
        return schema["default"]
    if "enum" in schema:
        return schema["enum"][0]
    name = parameter.get("name", "")
    typ = schema.get("type", "string")
    if name in UUIDS:
        return UUIDS[name]
    if name.endswith("_id") or schema.get("format") == "uuid":
        return sample_path_value(name)
    if name in ("page",):
        return 1
    if name in ("page_size", "limit"):
        return 20 if name == "page_size" else 30
    if name in ("date_from", "start_date"):
        return "2026-10-01"
    if name in ("date_to", "end_date"):
        return "2026-10-12"
    if name == "inactive_since":
        return "2026-10-01T00:00:00Z"
    if name == "timezone":
        return "Asia/Kolkata"
    if name == "search":
        return "Aarav"
    if name == "city":
        return "Pune"
    if name == "status":
        if "/notifications" in path:
            return "DELIVERED"
        if "/support/tickets" in path:
            return "OPEN"
    if name == "group_by":
        return "owner,city"
    if name == "cursor":
        return UUIDS["message_id"]
    if typ == "boolean":
        return True
    if typ == "integer":
        return 1
    if typ == "number":
        return 4.5
    if schema.get("format") == "date":
        return "2026-10-12"
    if schema.get("format") == "date-time":
        return "2026-10-12T10:30:00Z"
    return "example"


def deref_schema(schema, components):
    while "$ref" in schema:
        schema = components.get(schema["$ref"].rsplit("/", 1)[-1], {})
    return schema


def request_body_sample(operation, components, path):
    body_schema = (
        operation.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
    )
    if not body_schema:
        return None
    if path.endswith("/admin-auth/sign-in"):
        return {"email": "admin@example.test", "password": "{{adminPassword}}", "device_name": "Admin web"}
    if path.endswith("/admin-auth/mfa"):
        return {"challenge_id": UUIDS["preview_id"], "code": "123456"}
    if path.endswith("/admin-auth/refresh"):
        return {"refresh_token": "{{adminRefreshTokenAtLeast32Chars}}"}
    if path.endswith("/admin/users/{user_id}/status"):
        return {"is_active": False}
    if path.endswith("/garages/{garage_id}/status"):
        return {"operational_status": "SUSPENDED", "reason": "Safety review", "expected_version": 3}
    if path.endswith("/garages/{garage_id}/verification"):
        return {"verification_status": "VERIFIED", "reason": "Documents reviewed", "expected_version": 3}
    if path.endswith("/announcements/preview"):
        return {
            "audience": {"recipient_roles": ["GARAGE_OWNER"], "garage_ids": [], "city": "Pune",
                         "operational_status": "ACTIVE"},
            "channels": ["IN_APP"], "title": "Service update",
            "body": "New operating hours start Monday.",
        }
    if path.endswith("/admin/announcements"):
        return {"preview_id": UUIDS["preview_id"], "reason": "Scheduled maintenance notice"}
    if path.endswith("/staff/{admin_id}/roles"):
        return {
            "role_ids": ["role_support"],
            "data_scope": {"type": "PLATFORM", "garage_ids": []},
            "reason": "Assign customer support responsibilities",
        }
    if path.endswith("/support/tickets/{ticket_id}/assignment"):
        return {"assignee_id": UUIDS["admin_id"], "reason": "Assign to support queue", "expected_version": 2}
    if path.endswith("/support/tickets/{ticket_id}/priority"):
        return {"priority": "HIGH", "reason": "Customer cannot use vehicle", "expected_version": 2}
    if path.endswith("/support/tickets/{ticket_id}/status"):
        return {"status": "RESOLVED", "resolution": "Replacement part installed", "expected_version": 2}
    if path.endswith("/support/tickets/{ticket_id}/messages"):
        return {"client_message_id": "support-reply-demo-001", "text": "The garage has confirmed the appointment."}
    if path.endswith("/reports/exports"):
        return {
            "report_type": "OPERATIONS", "format": "CSV",
            "filters": {"date_from": "2026-10-01", "date_to": "2026-10-12", "timezone": "Asia/Kolkata",
                        "city": "Pune", "garage_id": None, "owner_id": None, "service_id": None},
            "snapshot_id": None, "exclude_inactive": False,
        }
    return sample_from_schema(body_schema, components)


def example_response(method, path, operation, components, data_schemas):
    status, data_schema = resolve_data_schema(operation, components)
    if method == "GET" and path.endswith("/reports/exports/{export_id}/download"):
        return status, None
    title = ""
    if "$ref" in data_schema:
        title = data_schema["$ref"].rsplit("/", 1)[-1]
    if title in data_schemas:
        data = data_schemas[title]
    elif "$ref" in data_schema:
        data = sample_from_schema(data_schema, components)
    elif data_schema.get("type") == "object" and data_schema.get("properties"):
        data = sample_from_schema(data_schema, components)
    elif data_schema and data_schema.get("type") == "array":
        data = sample_from_schema(data_schema, components)
    else:
        data = generic_data(method, path)
    code = int(status)
    message = "Created" if code == 201 else "Accepted" if code == 202 else "Success"
    if path.endswith("/users/{user_id}/status"):
        message = "Account status updated"
    if path.endswith("/support/tickets/{ticket_id}/messages") and method == "POST":
        code, message = 201, "Created successfully"
    if method == "POST" and path.endswith("/admin/announcements"):
        code, message = 202, "Success"
    if method == "POST" and path.endswith("/admin/reports/exports"):
        code, message = 202, "Success"
    return code, response(data, code, message)


def operation_example(method, path, operation, components, data_schemas):
    params = operation.get("parameters", [])
    concrete_path = path
    query = []
    for match in re.findall(r"{([^}]+)}", path):
        concrete_path = concrete_path.replace("{" + match + "}", sample_path_value(match))
    for parameter in params:
        if parameter.get("in") == "query":
            query.append((parameter["name"], sample_param(parameter, components, path)))
    url = BASE + concrete_path
    if query:
        query = [(key, str(value).lower() if isinstance(value, bool) else value) for key, value in query]
        url += "?" + urlencode(query)
    headers = []
    if path.startswith("/api/v1/admin/") or path.endswith("/admin-auth/logout"):
        headers.append("Authorization: Bearer {{admin_access_token}}")
    body = request_body_sample(operation, components, path)
    if body is not None:
        headers.append("Content-Type: application/json")
    for parameter in params:
        if parameter.get("in") == "header":
            header_name = parameter.get("name", "")
            headers.append(f"{header_name}: demo-idempotency-key-001")
    status, result = example_response(method, path, operation, components, data_schemas)
    return url, headers, body, status, result


def render_examples(openapi):
    components = openapi["components"]["schemas"]
    data_schemas = typed_data_examples()
    lines = [
        MARKER,
        "",
        "## Complete per-endpoint request and response examples",
        "",
        "The examples in this section are the concrete contracts for all 70 operations. They supersede the schema-only success summaries above. Every response is synthetic; it shows the response envelope and representative `data` fields, not live customer or production records.",
        "",
        "**Before using an example:** Replace each sample UUID with an existing record ID visible to the signed-in administrator. Replace `{{...}}` variables with values from the current auth response or secure client storage. These URLs use the production host, and write operations can change production data; do not send them as test requests.",
        "",
        "All JSON responses use the same envelope: `success`, `message`, `data`, `errors`, and `status_code`. GET operations have no request body; their example URL shows path and query values. `Idempotency-Key` is required for announcement send and report export.",
        "",
        "Some finance fields are permission-filtered. Financial values in these examples assume an administrator with the required `finance.read` permission; the customer payment-flag filter also requires it. Updating staff roles requires `security.manage` and a recent MFA check.",
        "",
    ]
    methods = ("get", "post", "put", "patch", "delete")
    ops = [
        (path, method, operation)
        for path, path_item in openapi["paths"].items()
        for method in methods
        if (operation := path_item.get(method))
    ]
    ops.sort(key=lambda item: (item[0].split("/")[3] if len(item[0].split("/")) > 3 else "", item[0], methods.index(item[1])))
    count = 0
    for path, method, operation in ops:
        count += 1
        summary = operation.get("summary") or operation.get("operationId") or path
        url, headers, body, status, result = operation_example(method.upper(), path, operation, components, data_schemas)
        lines += [
            f"### {method.upper()} {path}",
            "",
            f"**Endpoint:** `{url}`  ",
            "**Request headers:**",
            "",
            "```http",
            *(headers if headers else ["(none required)"]),
            "```",
            "",
            "**Request body:**",
            "",
        ]
        if body is None:
            lines += ["None."]
        else:
            lines += ["```json", json.dumps(body, indent=2, ensure_ascii=False), "```"]
        lines += ["", f"**Expected response: HTTP {status}**", ""]
        if result is None:
            lines += [
                "This endpoint returns a file download, not a JSON envelope. For a ready CSV export, the response has `Content-Type: text/csv`, `Content-Disposition: attachment; filename=\"operations.csv\"`, `Cache-Control: no-store`, and `X-Content-Type-Options: nosniff`.",
                "",
                "```text",
                "metadata,\"{...JSON report metadata...}\"",
                "booking_id,created_at,garage_id,status",
                f"{UUIDS['booking_id']},2026-10-12T10:00:00Z,{UUIDS['garage_id']},ACCEPTED",
                "```",
            ]
        else:
            lines += ["```json", json.dumps(result, indent=2, ensure_ascii=False), "```"]
        if path.endswith("/admin/staff/{admin_id}/roles"):
            lines += ["", "**Authorization note:** Requires `security.manage`, a recent MFA check, and a platform-scoped admin. Self role/scope changes are rejected."]
        if path.endswith("/admin/customers"):
            lines += ["", "**Permission note:** If `has_failed_payments` is supplied, the caller needs `finance.read`; otherwise that customer field is redacted."]
        if path.endswith("/admin/reports/exports/{export_id}/download"):
            lines += ["", "**Readiness note:** The export must have status `READY`; `QUEUED` or `PROCESSING` returns HTTP 409."]
        lines += ["", f"_Operation: {summary}. Replace the sample IDs and filters with values for the target record._", ""]
        lines += ["---", ""]
    if count != 70:
        raise RuntimeError(f"Expected 70 documented operations, generated {count}")
    return "\n".join(lines)


def update_markdown(content, appendix):
    if MARKER in content:
        content = content.split(MARKER, 1)[0].rstrip()
    return content.rstrip() + "\n\n" + appendix.rstrip() + "\n"


def inline_markup(value):
    value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    value = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', value)
    value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)
    return value


def build_pdf(markdown, output):
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="DocTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=20, leading=24, textColor=colors.HexColor("#12324A"), spaceAfter=14,
    ))
    styles.add(ParagraphStyle(
        name="H1Custom", parent=styles["Heading1"], fontSize=17, leading=21,
        textColor=colors.HexColor("#12324A"), spaceBefore=14, spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="H2Custom", parent=styles["Heading2"], fontSize=13, leading=16,
        textColor=colors.HexColor("#24556D"), spaceBefore=11, spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="H3Custom", parent=styles["Heading3"], fontSize=9.4, leading=12,
        textColor=colors.HexColor("#007A78"), spaceBefore=9, spaceAfter=4,
        keepWithNext=True,
    ))
    styles.add(ParagraphStyle(
        name="BodyCustom", parent=styles["BodyText"], fontSize=8.2, leading=11,
        spaceAfter=4, splitLongWords=True,
    ))
    styles.add(ParagraphStyle(
        name="BulletCustom", parent=styles["BodyText"], fontSize=8.1, leading=10.5,
        leftIndent=12, firstLineIndent=-7, spaceAfter=2,
    ))
    code_style = ParagraphStyle(
        name="CodeCustom", fontName="Courier", fontSize=6.1, leading=7.8,
        textColor=colors.HexColor("#1E293B"), backColor=colors.HexColor("#F3F6F8"),
        borderColor=colors.HexColor("#D8E1E7"), borderWidth=0.35, borderPadding=5,
        leftIndent=4, rightIndent=4, spaceBefore=3, spaceAfter=6,
    )
    story = []
    in_code = False
    code_lines = []
    paragraph_lines = []
    first_title = True

    def flush_paragraph():
        nonlocal paragraph_lines
        if paragraph_lines:
            text = " ".join(x.strip() for x in paragraph_lines)
            story.append(Paragraph(inline_markup(text), styles["BodyCustom"]))
            paragraph_lines = []

    def flush_code():
        nonlocal code_lines
        if code_lines:
            wrapped = []
            for line in code_lines:
                if not line:
                    wrapped.append("")
                    continue
                indent = len(line) - len(line.lstrip(" "))
                wrapped.extend(textwrap.wrap(
                    line, width=112, subsequent_indent=" " * min(indent + 2, 16),
                    break_long_words=True, break_on_hyphens=False,
                ) or [""])
            block = Preformatted("\n".join(wrapped), code_style, maxLineLength=112)
            story.append(block)
            code_lines = []

    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("```"):
            flush_paragraph()
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not line.strip():
            flush_paragraph()
            continue
        if line.strip() == "---":
            flush_paragraph()
            story.append(Spacer(1, 3))
            story.append(HRFlowable(width="100%", thickness=0.45, color=colors.HexColor("#CBD5E1")))
            story.append(Spacer(1, 4))
            continue
        heading = re.match(r"^(#{1,3})\s+(.*)$", line)
        if heading:
            flush_paragraph()
            level, text = len(heading.group(1)), heading.group(2)
            if level == 1:
                style = styles["DocTitle"] if first_title else styles["H1Custom"]
                first_title = False
            elif level == 2:
                style = styles["H2Custom"]
            else:
                style = styles["H3Custom"]
            story.append(Paragraph(inline_markup(text), style))
            continue
        if line.startswith("- "):
            flush_paragraph()
            story.append(Paragraph("• " + inline_markup(line[2:]), styles["BulletCustom"]))
            continue
        if line.startswith("> "):
            flush_paragraph()
            story.append(Paragraph(inline_markup(line[2:]), styles["BodyCustom"]))
            continue
        paragraph_lines.append(line)
    flush_paragraph()
    flush_code()

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(18 * mm, 11 * mm, "GoFixCarz Admin API — synthetic frontend examples")
        canvas.drawRightString(A4[0] - 18 * mm, 11 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(output), pagesize=A4, rightMargin=17 * mm, leftMargin=17 * mm,
        topMargin=16 * mm, bottomMargin=18 * mm,
        title="GoFixCarz Admin API — Production Frontend Handoff",
        author="GoFixCarz API documentation",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def main():
    markdown_path = DOCS / "GoFixCarz_Admin_API_Frontend_Contract.md"
    openapi_path = DOCS / "GoFixCarz_Admin_API_OpenAPI.json"
    pdf_path = DOCS / "GoFixCarz_Admin_API_Frontend_Contract.pdf"
    openapi = json.loads(openapi_path.read_text())
    content = markdown_path.read_text()
    appendix = render_examples(openapi)
    content = update_markdown(content, appendix)
    markdown_path.write_text(content)
    build_pdf(content, pdf_path)
    print(f"Generated examples for 70 operations.")
    print(f"Updated {markdown_path.name} ({len(content):,} characters).")
    print(f"Built {pdf_path.name} ({pdf_path.stat().st_size:,} bytes).")


if __name__ == "__main__":
    main()
