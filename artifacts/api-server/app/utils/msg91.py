import httpx
from loguru import logger
from app.core.config import settings


MSG91_URL = "https://api.msg91.com/api/sendhttp.php"


async def send_otp_sms(mobile: str, otp: str) -> bool:
    """
    Send an OTP SMS via MSG91.
    Returns True on success, False on failure.
    """
    message = (
        f"Your Skill Wallet platform account activation OTP is {otp}"
    )
    params = {
        "authkey": settings.MSG91_AUTH_KEY,
        "mobiles": mobile,
        "country": settings.MSG91_COUNTRY,
        "DLT_TE_ID": settings.MSG91_DLT_TE_ID,
        "message": message,
        "sender": settings.MSG91_SENDER,
        "route": settings.MSG91_ROUTE,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(MSG91_URL, params=params)
            response.raise_for_status()
            logger.info(f"OTP SMS sent to {mobile}: {response.text}")
            return True
    except Exception as e:
        logger.error(f"Failed to send OTP SMS to {mobile}: {e}")
        return False
