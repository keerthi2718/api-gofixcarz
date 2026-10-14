# Import all models to register them on Base.metadata
from app.models.admin_account import AdminAccount, AdminSession, AdminMfaChallenge, AdminRevokedFamily
from app.models.user import User
from app.models.garage import Garage
from app.models.customer import Customer
from app.models.vehicle import Vehicle
from app.models.booking import Booking
from app.models.job import Job
from app.models.job_timeline import JobTimeline
from app.models.service_package import ServicePackage
from app.models.notification import Notification
from app.models.refresh_token import RefreshToken
from app.models.sms_delivery import SMSDelivery
from app.models.admin_audit_log import AdminAuditLog
from app.models.admin_operations import CustomerAccount, AccountGarage, SourceRecord, SupportMessage, AdminResource
from app.models.customer_auth import (
    CustomerIdentity, CustomerSession, CustomerRefreshCredential,
    CustomerOTPChallenge, CustomerAuthRateBucket,
)
from app.database import admin_scope  # noqa: F401 — register the administrative scope guard

__all__ = [
    "User",
    "Garage",
    "Customer",
    "Vehicle",
    "Booking",
    "Job",
    "JobTimeline",
    "ServicePackage",
    "Notification",
    "RefreshToken",
    "SMSDelivery",
    "AdminAuditLog",
]
