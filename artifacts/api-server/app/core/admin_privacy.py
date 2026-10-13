import json
from fastapi.routing import APIRoute

FINANCE_KEYS = {
    "billing", "estimated_amount", "final_amount", "completed_job_amount_paise",
    "revenue", "revenue_this_month", "revenue_last_month", "revenue_growth_percent",
    "invoice_id", "payment_id", "gross_collected_amount", "refunded_amount",
    "net_collected_amount", "issued_invoice_total_amount", "average_invoice_amount",
    "paid_invoice_count", "issued_invoice_count", "failed_attempts",
    "has_failed_payments",
    "total_revenue", "parent_id",
}


class AdminPrivacyRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            response = await original(request)
            if not hasattr(response, "body") or "application/json" not in response.headers.get("content-type", ""):
                return response
            access = getattr(request.state, "admin_access", {})
            finance = "finance.read" in access.get("permissions", [])
            restricted = set()

            def redact(value):
                if isinstance(value, list):
                    return [redact(item) for item in value]
                if not isinstance(value, dict):
                    return value
                result = {}
                for key, item in value.items():
                    if any(word in key.lower() for word in (
                        "password", "otp", "secret", "token", "credential", "authorization", "cookie",
                    )):
                        result[key] = "[REDACTED]"
                    elif not finance and (key in FINANCE_KEYS or key.startswith("revenue")):
                        restricted.add(key)
                        result[key] = None
                    else:
                        result[key] = redact(item)
                return result

            body = redact(json.loads(response.body))
            if restricted and isinstance(body.get("data"), dict):
                body["data"]["restricted_fields"] = sorted(restricted)
            response.body = json.dumps(body, separators=(",", ":")).encode()
            response.headers["content-length"] = str(len(response.body))
            response.headers["cache-control"] = "no-store"
            return response
        return handler
