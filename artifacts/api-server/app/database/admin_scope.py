"""Apply tenant scope to ORM reads, including aggregates and eager relationships."""
from sqlalchemy import event, select
from sqlalchemy.orm import Session, with_loader_criteria


@event.listens_for(Session, "do_orm_execute")
def admin_scope(execution):
    access = execution.session.info.get("admin_access")
    if not execution.is_select or not access or access["garage_ids"] is None:
        return
    from app.models.garage import Garage
    from app.models.user import User
    from app.models.job import Job
    from app.models.booking import Booking
    from app.models.customer import Customer
    from app.models.vehicle import Vehicle
    from app.models.notification import Notification
    from app.models.job_timeline import JobTimeline
    from app.models.admin_operations import SourceRecord, CustomerAccount, AccountGarage
    ids = access["garage_ids"]
    owner_ids = select(Garage.user_id).where(Garage.id.in_(ids))
    account_ids = select(AccountGarage.account_id).where(AccountGarage.garage_id.in_(ids))
    job_ids = select(Job.id).where(Job.garage_id.in_(ids))
    criteria = [
        (Garage, Garage.id.in_(ids)), (User, User.id.in_(owner_ids)),
        (JobTimeline, JobTimeline.job_id.in_(job_ids)),
        (CustomerAccount, CustomerAccount.id.in_(account_ids)),
    ] + [(model, model.garage_id.in_(ids)) for model in
         (Job, Booking, Customer, Vehicle, Notification, SourceRecord, AccountGarage)]
    execution.statement = execution.statement.options(*[
        with_loader_criteria(model, condition, include_aliases=True) for model, condition in criteria
    ])
