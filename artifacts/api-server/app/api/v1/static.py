from fastapi import APIRouter

from app.schemas.response import APIResponse

router = APIRouter()

_PRIVACY_POLICY = """
# Privacy Policy

Last updated: January 1, 2025

## Information We Collect
We collect information you provide directly to us when you register for an account, including your name, mobile number, and email address.

## How We Use Your Information
We use the information we collect to operate and improve our garage management service, send you transactional SMS messages (OTP verification), and provide customer support.

## Data Security
We implement industry-standard security measures to protect your personal information. Your data is stored securely and is never sold to third parties.

## Contact Us
If you have any questions about this Privacy Policy, please contact us through the app's support section.
""".strip()

_HELP_SUPPORT = """
# Help & Support

## Getting Started
1. Sign up with your mobile number
2. Verify the OTP sent to your phone
3. Set up your garage profile
4. Start adding customers and vehicles

## Common Questions

**How do I add a customer?**
Navigate to Customers → tap the + button → fill in the customer details.

**How do I create a job?**
Go to Jobs → tap New Job → select the customer and vehicle → add a description.

**How do I track job status?**
Open any job and use the Status Update button to move it through the workflow: OPEN → IN_PROGRESS → QUALITY_CHECK → COMPLETED.

**What are bookings?**
Bookings are appointment requests that come in externally. You can accept or reject them, or convert them directly into jobs.

## Contact Support
For technical assistance, please email support@garage-app.example.com or call our helpline at 1800-GARAGE.
""".strip()


@router.get("/privacy-policy", response_model=APIResponse)
async def privacy_policy():
    """Return the app privacy policy."""
    return APIResponse.ok(data={"content": _PRIVACY_POLICY}, message="Privacy policy retrieved")


@router.get("/help-support", response_model=APIResponse)
async def help_support():
    """Return help and support information."""
    return APIResponse.ok(data={"content": _HELP_SUPPORT}, message="Help & support retrieved")
