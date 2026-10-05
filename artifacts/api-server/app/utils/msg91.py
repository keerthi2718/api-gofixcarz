import httpx
import re
import logging
from loguru import logger
from app.core.config import settings


MSG91_URL = "https://api.msg91.com/api/sendhttp.php"
# HTTPX logs request URLs at INFO, including the recipient and OTP parameters.
logging.getLogger("httpx").setLevel(logging.WARNING)


async def send_otp_sms(mobile: str, otp: str) -> bool:
    """Compatibility wrapper; acceptance is not proof of handset delivery."""
    return await submit_otp_sms(mobile, otp) is not None


async def submit_otp_sms(mobile: str, otp: str) -> str | None:
    """
    Send an OTP SMS via MSG91.
    Return the provider request ID on acceptance, otherwise None.
    """
    # Preserve the exact legacy template requested by the user.
    # HTTPX encodes parameters once; never interpolate credentials into a URL.
    params = {
        "authkey": settings.MSG91_AUTH_KEY,
        "mobiles": mobile,
        "country": settings.MSG91_COUNTRY,
        "DLT_TE_ID": settings.MSG91_DLT_TE_ID,
        "message": f"Your Skill Wallet platform account activation OTP is {otp}",
        "sender": settings.MSG91_SENDER,
        "route": settings.MSG91_ROUTE,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                MSG91_URL,
                params=params,
            )
            response.raise_for_status()
            # The legacy endpoint defaults to a plain 24-character hex SMS ID.
            # Numeric error codes and arbitrary HTTP-200 bodies are not success.
            text = response.text.strip()
            if re.fullmatch(r"[A-Fa-f0-9]{24}", text):
                logger.info("MSG91 accepted OTP request; request_id={}", text)
                return text
            try:
                result = response.json()
            except ValueError:
                logger.warning("MSG91 returned an invalid OTP submission response")
                return None

            if not isinstance(result, dict):
                logger.warning("MSG91 returned an invalid OTP submission response")
                return None
            request_id = result.get("message")
            if (
                str(result.get("type", "")).lower() == "success"
                and isinstance(request_id, str)
                and re.fullmatch(r"[A-Fa-f0-9]{24}", request_id)
            ):
                logger.info("MSG91 accepted OTP request; request_id={}", request_id)
                return request_id

            # Never log the response body, OTP, phone, auth key, or request URL.
            code = str(result.get("code", "unknown"))
            safe_code = code if re.fullmatch(r"\d{1,6}", code) else "unknown"
            logger.warning("MSG91 rejected OTP submission; provider_code={}", safe_code)
            return None
    except httpx.HTTPStatusError as exc:
        logger.error("MSG91 OTP submission failed; http_status={}", exc.response.status_code)
        return None
    except Exception as exc:
        logger.error("MSG91 OTP submission failed; error_type={}", type(exc).__name__)
        return None
