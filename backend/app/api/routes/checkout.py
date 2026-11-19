import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from typing import Optional, Dict, Any
from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

try:
    import stripe
    HAS_STRIPE = True
except ImportError:
    HAS_STRIPE = False

logger = logging.getLogger("opspilot.checkout")

router = APIRouter(tags=["Payment Gateway & Checkout"])

# Environment Secrets Management
PAYMENT_WEBHOOK_SECRET = os.getenv("PAYMENT_WEBHOOK_SECRET", "whsec_test_mock_webhook_secret_shopflow_2026_strict")
PAYMENT_GATEWAY_API_KEY = os.getenv("PAYMENT_GATEWAY_API_KEY", "sk_test_shopflow_mock_gateway_api_key_2026")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", PAYMENT_GATEWAY_API_KEY)
if HAS_STRIPE and STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

class PaymentIntentRequest(BaseModel):
    order_id: str = Field(..., description="Target order identifier")
    amount: float = Field(..., gt=0, description="Amount in currency units (e.g. USD)")
    currency: str = Field("usd", description="Three-letter ISO currency code")
    customer_email: str = Field(..., description="Customer email for payment receipt")
    idempotency_key: Optional[str] = Field(None, description="Client idempotency key")

class PaymentIntentResponse(BaseModel):
    id: str
    client_secret: str
    order_id: str
    amount: float
    currency: str
    status: str
    mode: str = "test"
    created_at: int
    livemode: bool = False

# In-memory payment ledger & processed webhook registry for idempotency
payment_intents: Dict[str, Dict[str, Any]] = {}
processed_webhook_events: set = set()


@router.post(
    "/checkout/payment-intent",
    response_model=PaymentIntentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create test-mode payment intent with idempotency support"
)
@router.post(
    "/api/checkout/payment-intent",
    response_model=PaymentIntentResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False
)
def create_payment_intent(req: PaymentIntentRequest):
    """
    Creates a Payment Intent supporting idempotency.
    If STRIPE_SECRET_KEY is configured in the environment, attempts creation via Stripe's API.
    Otherwise, generates a deterministic test-mode payment intent (pi_test_...).
    """
    # 1. Check client idempotency key
    if req.idempotency_key and req.idempotency_key in payment_intents:
        cached = payment_intents[req.idempotency_key]
        logger.info(f"Payment intent idempotency cache hit for key {req.idempotency_key}")
        return PaymentIntentResponse(**cached)

    intent_id = f"pi_test_{uuid.uuid4().hex[:16]}"
    client_secret = f"{intent_id}_secret_{uuid.uuid4().hex[:16]}"
    now_ts = int(time.time())
    is_live = False

    # 2. If genuine STRIPE_SECRET_KEY is configured, interact with Stripe API
    if STRIPE_SECRET_KEY and (STRIPE_SECRET_KEY.startswith("sk_test_") or STRIPE_SECRET_KEY.startswith("sk_live_")):
        try:
            import httpx
            with httpx.Client(timeout=4.0) as client:
                res = client.post(
                    "https://api.stripe.com/v1/payment_intents",
                    auth=(STRIPE_SECRET_KEY, ""),
                    data={
                        "amount": int(round(req.amount * 100)),
                        "currency": req.currency.lower(),
                        "description": f"OpsPilot Order {req.order_id}",
                        "metadata[order_id]": req.order_id,
                        "metadata[customer_email]": req.customer_email
                    }
                )
                if res.status_code in (200, 201):
                    s_data = res.json()
                    intent_id = s_data.get("id", intent_id)
                    client_secret = s_data.get("client_secret", client_secret)
                    is_live = s_data.get("livemode", False)
        except Exception as e:
            logger.warning(f"Live Stripe API request failed ({e}); falling back to test-mode intent simulation")

    intent_data = {
        "id": intent_id,
        "client_secret": client_secret,
        "order_id": req.order_id,
        "amount": req.amount,
        "currency": req.currency.lower(),
        "status": "requires_payment_method",
        "mode": "test" if not is_live else "live",
        "created_at": now_ts,
        "livemode": is_live,
        "customer_email": req.customer_email
    }

    if req.idempotency_key:
        payment_intents[req.idempotency_key] = intent_data
    payment_intents[intent_id] = intent_data

    logger.info(f"Created payment intent {intent_id} for order {req.order_id} (${req.amount})")
    return PaymentIntentResponse(**intent_data)


@router.post(
    "/checkout/webhook/payment",
    status_code=status.HTTP_200_OK,
    summary="Signature-verified payment gateway webhook receiver"
)
@router.post(
    "/api/checkout/webhook/payment",
    status_code=status.HTTP_200_OK,
    include_in_schema=False
)
async def payment_webhook(
    request: Request,
    x_signature: Optional[str] = Header(None, alias="X-Signature"),
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature")
):
    """
    Signature-verified webhook receiver.
    Supports:
    - Official Stripe webhook signatures: t=<timestamp>,v1=<signature>
    - Direct HMAC-SHA256 hex signatures: X-Signature: <hex>
    - Constant-time comparison to prevent timing attacks.
    - Idempotent duplicate event suppression.
    """
    signature = x_signature or stripe_signature
    if not signature:
        logger.warning("Missing required signature header (X-Signature or Stripe-Signature)")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing signature header for payment webhook"
        )

    raw_body = await request.body()
    is_valid = False

    # Check for Stripe standard header format: t=<timestamp>,v1=<hmac_hex>
    if "t=" in signature and "v1=" in signature:
        pairs = dict(item.strip().split("=", 1) for item in signature.split(",") if "=" in item)
        t = pairs.get("t")
        v1 = pairs.get("v1")
        if t and v1:
            signed_payload = f"{t}.".encode("utf-8") + raw_body
            expected_v1 = hmac.new(
                PAYMENT_WEBHOOK_SECRET.encode("utf-8"),
                signed_payload,
                hashlib.sha256
            ).hexdigest()
            if hmac.compare_digest(v1.strip(), expected_v1):
                is_valid = True

    # Fallback to direct raw HMAC-SHA256 comparison
    if not is_valid:
        computed_sig = hmac.new(
            PAYMENT_WEBHOOK_SECRET.encode("utf-8"),
            raw_body,
            hashlib.sha256
        ).hexdigest()
        if hmac.compare_digest(signature.strip(), computed_sig):
            is_valid = True

    if not is_valid:
        logger.error("Cryptographic webhook signature mismatch!")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cryptographic signature verification failed"
        )

    try:
        event = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed JSON in webhook body: {str(e)}"
        )

    event_type = event.get("type", "unknown")
    event_id = event.get("id") or f"{event_type}_{event.get('data', {}).get('object', {}).get('id', uuid.uuid4().hex)}"

    # Idempotent Duplicate-Event Handling
    if event_id in processed_webhook_events:
        logger.info(f"Duplicate webhook event {event_id} ignored idempotently.")
        return {
            "received": True,
            "event_type": event_type,
            "event_id": event_id,
            "duplicate": True,
            "message": "Duplicate webhook event ignored idempotently.",
            "processed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }

    processed_webhook_events.add(event_id)

    # Process status transition
    intent_obj = event.get("data", {}).get("object", {})
    intent_id = intent_obj.get("id")

    if event_type == "payment_intent.succeeded":
        if intent_id and intent_id in payment_intents:
            payment_intents[intent_id]["status"] = "succeeded"
    elif event_type == "payment_intent.payment_failed":
        if intent_id and intent_id in payment_intents:
            payment_intents[intent_id]["status"] = "failed"

    return {
        "received": True,
        "event_type": event_type,
        "event_id": event_id,
        "status": "processed",
        "processed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }


@router.get(
    "/checkout/payment-intents/{intent_id}",
    response_model=PaymentIntentResponse,
    summary="Retrieve payment intent details"
)
@router.get(
    "/api/checkout/payment-intents/{intent_id}",
    response_model=PaymentIntentResponse,
    include_in_schema=False
)
def get_payment_intent(intent_id: str):
    """Retrieves current payment intent status."""
    if intent_id not in payment_intents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payment intent '{intent_id}' not found"
        )
    return PaymentIntentResponse(**payment_intents[intent_id])
