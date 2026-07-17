"""
Seed script — populates the database with representative sample data.

Usage:
    cd artifacts/api-server
    python -m app.utils.seed

The script is idempotent for the seed user (keyed on mobile 9000000000).
"""

import asyncio
import random
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.database.session import async_session
from app.models.booking import Booking, BookingStatus
from app.models.customer import Customer
from app.models.garage import Garage
from app.models.job import Job, JobStatus
from app.models.job_timeline import JobTimeline
from app.models.notification import Notification
from app.models.service_package import ServicePackage
from app.models.user import User
from app.models.vehicle import Vehicle


SEED_MOBILE = "9000000000"

CUSTOMER_DATA = [
    {"name": "Ravi Kumar",    "mobile": "9111111001", "email": "ravi@example.com"},
    {"name": "Priya Sharma",  "mobile": "9111111002", "email": "priya@example.com"},
    {"name": "Anjali Singh",  "mobile": "9111111003", "email": None},
    {"name": "Deepak Verma",  "mobile": "9111111004", "email": "deepak@example.com"},
    {"name": "Sunita Rao",    "mobile": "9111111005", "email": None},
]

VEHICLE_DATA = [
    # (make, model, year, plate, colour)
    ("Maruti",   "Swift",     2021, "MH01AA0001", "Red"),
    ("Hyundai",  "i20",       2022, "MH01BB0002", "White"),
    ("Tata",     "Nexon",     2023, "MH01CC0003", "Blue"),
    ("Honda",    "City",      2020, "MH01DD0004", "Silver"),
    ("Toyota",   "Innova",    2019, "MH01EE0005", "Grey"),
    ("Ford",     "EcoSport",  2021, "MH01FF0006", "Black"),
    ("Kia",      "Seltos",    2022, "MH01GG0007", "White"),
    ("MG",       "Hector",    2020, "MH01HH0008", "Red"),
    ("Skoda",    "Octavia",   2023, "MH01II0009", "Blue"),
    ("VW",       "Polo",      2018, "MH01JJ0010", "Silver"),
]

JOB_DESCRIPTIONS = [
    "Full service and oil change",
    "Brake pads replacement",
    "AC repair and gas refill",
    "Tyre rotation and alignment",
    "Battery replacement",
    "Engine tune-up",
    "Suspension check",
    "Transmission service",
    "Coolant flush",
    "Windshield repair",
    "Electrical fault diagnosis",
    "Clutch replacement",
    "Headlight restoration",
    "Exhaust system repair",
    "Power steering fluid service",
    "Differential oil change",
    "Spark plug replacement",
    "Timing belt service",
    "Fuel system cleaning",
    "Pre-purchase inspection",
]

STATUSES = [
    JobStatus.OPEN,
    JobStatus.IN_PROGRESS,
    JobStatus.IN_PROGRESS,
    JobStatus.WAITING_FOR_PARTS,
    JobStatus.QUALITY_CHECK,
    JobStatus.COMPLETED,
    JobStatus.COMPLETED,
    JobStatus.COMPLETED,
    JobStatus.CANCELLED,
    JobStatus.OPEN,
]

SERVICE_PACKAGES = [
    {"name": "Basic Service",          "description": "Oil, filter & inspection",           "price": 1499, "duration_minutes": 120},
    {"name": "Standard Service",       "description": "Basic + brake & tyre check",         "price": 2499, "duration_minutes": 180},
    {"name": "Comprehensive Service",  "description": "Full vehicle health check",           "price": 3999, "duration_minutes": 240},
    {"name": "AC Service",             "description": "Gas refill + filter clean",           "price": 1999, "duration_minutes": 90},
    {"name": "Express Wash & Polish",  "description": "Exterior wash and wax polish",        "price": 799,  "duration_minutes": 60},
]

NOTIFICATION_DATA = [
    {"title": "New Booking",          "message": "You have received a new booking request from Ravi Kumar.",   "type": "booking"},
    {"title": "Job Completed",        "message": "Job JOB-20260701-0001 has been marked as completed.",        "type": "job"},
    {"title": "Parts Arrived",        "message": "Spare parts for Job JOB-20260701-0002 have arrived.",         "type": "info"},
    {"title": "Booking Accepted",     "message": "Priya Sharma's booking has been accepted.",                  "type": "booking"},
    {"title": "Monthly Summary",      "message": "Your garage completed 24 jobs this month with ₹89,450 revenue.", "type": "info"},
    {"title": "Payment Received",     "message": "Payment of ₹3,999 received for job JOB-20260701-0003.",      "type": "payment"},
    {"title": "Customer Review",      "message": "Anjali Singh left a 5-star rating for your service.",         "type": "review"},
    {"title": "Service Due",          "message": "Vehicle MH01AA0001 is due for its next service.",             "type": "reminder"},
    {"title": "New Customer",         "message": "Deepak Verma has registered as a new customer.",              "type": "customer"},
    {"title": "System Update",        "message": "The app has been updated with new features.",                  "type": "system"},
]


async def seed():
    async with async_session() as session:
        # ── User ─────────────────────────────────────────────────────────────
        user = (
            await session.execute(select(User).where(User.mobile == SEED_MOBILE))
        ).scalar_one_or_none()
        if not user:
            user = User(id=uuid.uuid4(), name="Garage Owner", mobile=SEED_MOBILE, is_active=True)
            session.add(user)
            await session.flush()
            print(f"  ✓ User created: {user.mobile}")
        else:
            print(f"  • User exists: {user.mobile}")

        # ── Garage ───────────────────────────────────────────────────────────
        garage = (
            await session.execute(select(Garage).where(Garage.user_id == user.id, Garage.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if not garage:
            garage = Garage(
                id=uuid.uuid4(),
                user_id=user.id,
                name="AutoCare Garage",
                owner="Garage Owner",
                address="Plot 42, MIDC Industrial Area, Pune - 411018",
                working_hours={
                    "mon": "09:00-18:00",
                    "tue": "09:00-18:00",
                    "wed": "09:00-18:00",
                    "thu": "09:00-18:00",
                    "fri": "09:00-18:00",
                    "sat": "09:00-14:00",
                    "sun": "closed",
                },
                latitude=18.5204,
                longitude=73.8567,
            )
            session.add(garage)
            await session.flush()
            print(f"  ✓ Garage created: {garage.name}")
        else:
            print(f"  • Garage exists: {garage.name}")

        # ── Customers ────────────────────────────────────────────────────────
        customers = []
        for cd in CUSTOMER_DATA:
            existing = (
                await session.execute(
                    select(Customer).where(Customer.mobile == cd["mobile"], Customer.garage_id == garage.id)
                )
            ).scalar_one_or_none()
            if not existing:
                c = Customer(id=uuid.uuid4(), garage_id=garage.id, **cd)
                session.add(c)
                await session.flush()
                customers.append(c)
            else:
                customers.append(existing)
        print(f"  ✓ Customers ready: {len(customers)}")

        # ── Vehicles ─────────────────────────────────────────────────────────
        vehicles = []
        for i, (make, model, year, plate, colour) in enumerate(VEHICLE_DATA):
            existing = (
                await session.execute(
                    select(Vehicle).where(Vehicle.registration_plate == plate, Vehicle.garage_id == garage.id)
                )
            ).scalar_one_or_none()
            if not existing:
                customer = customers[i % len(customers)]
                v = Vehicle(
                    id=uuid.uuid4(),
                    garage_id=garage.id,
                    customer_id=customer.id,
                    make=make,
                    model=model,
                    year=year,
                    registration_plate=plate,
                    colour=colour,
                )
                session.add(v)
                await session.flush()
                vehicles.append(v)
            else:
                vehicles.append(existing)
        print(f"  ✓ Vehicles ready: {len(vehicles)}")

        # ── Jobs ─────────────────────────────────────────────────────────────
        job_count_existing = (
            await session.execute(
                select(Job).where(Job.garage_id == garage.id)
            )
        ).scalars().all()

        if len(job_count_existing) < 20:
            for i in range(20):
                today = datetime.now(timezone.utc)
                created_at = today - timedelta(days=random.randint(0, 30))
                status = STATUSES[i % len(STATUSES)]
                vehicle = vehicles[i % len(vehicles)]
                customer_id = vehicle.customer_id
                estimated = random.choice([999, 1499, 1999, 2499, 3499, 4999])
                final = estimated + random.randint(-200, 500) if status == JobStatus.COMPLETED else None
                completed_at = created_at + timedelta(hours=random.randint(2, 8)) if status == JobStatus.COMPLETED else None

                job_number = f"JOB-{created_at.strftime('%Y%m%d')}-{i + 1:04d}"
                job = Job(
                    id=uuid.uuid4(),
                    garage_id=garage.id,
                    customer_id=customer_id,
                    vehicle_id=vehicle.id,
                    job_number=job_number,
                    status=status,
                    description=JOB_DESCRIPTIONS[i],
                    estimated_amount=estimated,
                    final_amount=final,
                    completed_at=completed_at,
                )
                session.add(job)
                await session.flush()

                # Initial timeline entry
                session.add(JobTimeline(
                    id=uuid.uuid4(), job_id=job.id, status=JobStatus.OPEN.value, notes="Job created"
                ))
                if status not in (JobStatus.OPEN,):
                    session.add(JobTimeline(
                        id=uuid.uuid4(), job_id=job.id, status=status.value, notes="Status updated"
                    ))
                await session.flush()
            print("  ✓ Jobs seeded: 20")
        else:
            print(f"  • Jobs already exist: {len(job_count_existing)}")

        # ── Bookings ─────────────────────────────────────────────────────────
        booking_count = (
            await session.execute(
                select(Booking).where(Booking.garage_id == garage.id)
            )
        ).scalars().all()

        if len(booking_count) < 5:
            booking_statuses = [BookingStatus.PENDING, BookingStatus.ACCEPTED, BookingStatus.REJECTED, BookingStatus.PENDING, BookingStatus.CONVERTED]
            for i, bstatus in enumerate(booking_statuses):
                customer = customers[i % len(customers)]
                b = Booking(
                    id=uuid.uuid4(),
                    garage_id=garage.id,
                    customer_id=customer.id if bstatus != BookingStatus.PENDING else None,
                    vehicle_id=vehicles[i].id if bstatus != BookingStatus.PENDING else None,
                    status=bstatus,
                    booking_date=date.today() + timedelta(days=i),
                    customer_name=customer.name,
                    customer_mobile=customer.mobile,
                    service_requested=JOB_DESCRIPTIONS[i],
                )
                session.add(b)
            await session.flush()
            print("  ✓ Bookings seeded: 5")
        else:
            print(f"  • Bookings already exist: {len(booking_count)}")

        # ── Service Packages ─────────────────────────────────────────────────
        pkg_count = (
            await session.execute(
                select(ServicePackage).where(ServicePackage.garage_id == garage.id, ServicePackage.deleted_at.is_(None))
            )
        ).scalars().all()

        if len(pkg_count) < 5:
            for pd in SERVICE_PACKAGES:
                session.add(ServicePackage(
                    id=uuid.uuid4(),
                    garage_id=garage.id,
                    name=pd["name"],
                    description=pd["description"],
                    price=pd["price"],
                    duration_minutes=pd["duration_minutes"],
                    is_active=True,
                ))
            await session.flush()
            print("  ✓ Service packages seeded: 5")
        else:
            print(f"  • Service packages already exist: {len(pkg_count)}")

        # ── Notifications ────────────────────────────────────────────────────
        notif_count = (
            await session.execute(
                select(Notification).where(Notification.garage_id == garage.id)
            )
        ).scalars().all()

        if len(notif_count) < 10:
            for i, nd in enumerate(NOTIFICATION_DATA):
                n = Notification(
                    id=uuid.uuid4(),
                    garage_id=garage.id,
                    title=nd["title"],
                    message=nd["message"],
                    type=nd["type"],
                    # Mark half as read
                    read_at=datetime.now(timezone.utc) if i < 5 else None,
                )
                session.add(n)
            await session.flush()
            print("  ✓ Notifications seeded: 10")
        else:
            print(f"  • Notifications already exist: {len(notif_count)}")

        await session.commit()
        print("\n✅ Seed complete!")
        print(f"   Mobile: {SEED_MOBILE}")
        print("   Use POST /api/v1/auth/sign-in to request an OTP, then verify to get a JWT.")


if __name__ == "__main__":
    print("🌱 Seeding database...")
    asyncio.run(seed())
