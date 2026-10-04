# Import all models to register them on Base.metadata
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
]
