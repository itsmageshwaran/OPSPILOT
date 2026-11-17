import os
import time
import hmac
import hashlib
import uuid
import json
from fastapi import FastAPI, HTTPException, Header, Request, status
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from services.common.db import db
from telemetry.logger import get_logger
from chaos.engine import chaos_engine

logger = get_logger("checkout-api")

# ==============================================================================
# Environment Variables & Secrets Management: Payment Gateway
# Secret keys for payment processing and webhook signature verification.
# Insecure hardcoded production secrets are strictly prevented.
# ==============================================================================
PAYMENT_GATEWAY_API_KEY = os.getenv("PAYMENT_GATEWAY_API_KEY")
PAYMENT_WEBHOOK_SECRET = os.getenv("PAYMENT_WEBHOOK_SECRET")

if not PAYMENT_WEBHOOK_SECRET:
    if os.getenv("ENVIRONMENT", "").lower() in ("production", "prod"):
        raise RuntimeError(
            "FATAL: PAYMENT_WEBHOOK_SECRET must be provided via environment variables in production."
        )
    PAYMENT_WEBHOOK_SECRET = "whsec_test_mock_webhook_secret_shopflow_2026_strict"

if not PAYMENT_GATEWAY_API_KEY:
    PAYMENT_GATEWAY_API_KEY = "sk_test_shopflow_mock_gateway_api_key_2026"

app = FastAPI(
    title="ShopFlow Checkout API",
    version="1.0.0",
    description="Checkout and payment orchestration microservice supporting test-mode intent generation and signature-verified webhooks."
)

class CartItem(BaseModel):
    product_id: str
    product_title: Optional[str] = None
    price: float
    quantity: int = 1
    image_url: Optional[str] = None

class CartRequest(BaseModel):
    session_id: str
    items: List[CartItem]

class CheckoutRequest(BaseModel):
    user_id: Optional[str] = "usr_alex_01"
    user_email: Optional[str] = "alex@shopflow.dev"
    items: List[CartItem]
    shipping_address: Dict[str, Any]
    payment_method: Optional[str] = "Credit Card (Simulated)"
    coupon_code: Optional[str] = None

class CheckoutResponse(BaseModel):
    success: bool
    order_id: Optional[str] = None
    message: str
    order: Optional[Dict[str, Any]] = None

# ------------------------------------------------------------------------------
# Payment Gateway Integration: Test-Mode Checkout & Webhooks
# ------------------------------------------------------------------------------
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

# In-memory test payment ledger for idempotent intent tracking
payment_intents: Dict[str, Dict[str, Any]] = {}


@app.get("/health")
def health():
    chaos_status = chaos_engine.get_status()
    if (
        chaos_status.get("active_scenario") in ["database_cascade", "checkout_failure"] and
        chaos_status.get("current_stage", 0) >= 4 and
        chaos_status.get("state") in ["RUNNING", "COMPLETED"]
    ):
        return {
            "status": "degraded",
            "service": "checkout-api",
            "dependencies": {
                "order-api": "degraded",
                "product-api": "healthy",
                "postgresql": "failing"
            }
        }
    return {
        "status": "healthy",
        "service": "checkout-api",
        "dependencies": {
            "order-api": "healthy",
            "product-api": "healthy",
            "postgresql": "healthy"
        }
    }

@app.post("/cart")
def update_cart(request: CartRequest):
    db.save_cart(request.session_id, [item.model_dump() for item in request.items])
    return {"status": "ok", "items_count": len(request.items)}

@app.get("/cart/{session_id}")
def get_cart(session_id: str):
    items = db.get_cart(session_id)
    return {"session_id": session_id, "items": items}

@app.post("/checkout", response_model=CheckoutResponse)
def process_checkout(request: CheckoutRequest):
    start = time.time()
    logger.info("CHECKOUT_INITIATED", f"Initiating checkout for {request.user_email}", metadata={"items_count": len(request.items)})

    if not request.items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    chaos_status = chaos_engine.get_status()

    # 1. Simulate High Memory latency
    if chaos_status.get("active_scenario") == "high_memory" and chaos_status.get("state") == "RUNNING":
        time.sleep(0.35)

    # 2. Simulate Isolated Checkout Failure
    if chaos_status.get("active_scenario") == "checkout_failure" and chaos_status.get("state") in ["RUNNING", "COMPLETED"]:
        latency = (time.time() - start) * 1000
        logger.error("PAYMENT_GATEWAY_ERROR", "Payment simulator rejected transaction: simulated upstream gateway error", status_code=500, latency_ms=latency)
        raise HTTPException(status_code=500, detail="Payment authorization rejected by gateway.")

    # 3. Simulate Database Cascade Downstream Failure (Stage 4+)
    if (
        chaos_status.get("active_scenario") == "database_cascade" and
        chaos_status.get("current_stage", 0) >= 3 and
        chaos_status.get("state") in ["RUNNING", "COMPLETED"]
    ):
        time.sleep(0.4)
        latency = (time.time() - start) * 1000
        logger.error(
            "DEPENDENCY_TIMEOUT",
            "Checkout API call to downstream order-api timed out after 3000ms",
            dependency="order-api",
            latency_ms=latency,
            status_code=503
        )
        logger.error(
            "CHECKOUT_FAILED",
            "Checkout workflow aborting due to order persistence failure in order-api",
            dependency="order-api",
            status_code=503
        )
        raise HTTPException(
            status_code=503,
            detail="Checkout temporarily unavailable. Your cart is safe. Please try again in a moment."
        )

    # Calculate Totals
    subtotal = sum(item.price * item.quantity for item in request.items)
    if request.coupon_code and request.coupon_code.upper() == "HACKATHON20":
        subtotal = round(subtotal * 0.8, 2)
    tax = round(subtotal * 0.08, 2)
    shipping = 0.00 if subtotal > 50.0 else 9.99
    total = round(subtotal + tax + shipping, 2)

    # Verify inventory from DB
    for item in request.items:
        prod = db.get_product(item.product_id)
        if prod and prod["stock"] < item.quantity:
            logger.warn("INSUFFICIENT_STOCK", f"Insufficient stock for {prod['title']}", latency_ms=(time.time() - start) * 1000)
            raise HTTPException(status_code=400, detail=f"Insufficient stock for {prod['title']}")

    # Call Order API / DB to create the order
    order_payload = {
        "user_id": request.user_id or "usr_alex_01",
        "user_email": request.user_email or "alex@shopflow.dev",
        "subtotal": subtotal,
        "tax": tax,
        "shipping": shipping,
        "total": total,
        "shipping_address": request.shipping_address,
        "payment_method": request.payment_method or "Credit Card (Simulated)",
        "items": [
            {
                "product_id": item.product_id,
                "product_title": item.product_title or (db.get_product(item.product_id) or {}).get("title", "Product"),
                "price": item.price,
                "quantity": item.quantity
            }
            for item in request.items
        ]
    }

    created_order = db.create_order(order_payload)
    latency = (time.time() - start) * 1000
    logger.info("CHECKOUT_COMPLETED", f"Checkout succeeded. Order {created_order['id']} placed.", latency_ms=latency, status_code=200)

    return CheckoutResponse(
        success=True,
        order_id=created_order["id"],
        message="Order successfully placed!",
        order=created_order
    )

# ------------------------------------------------------------------------------
# Payment Gateway Endpoints: Test-Mode Intent Creation & Webhooks
# ------------------------------------------------------------------------------
@app.post(
    "/checkout/payment-intent",
    response_model=PaymentIntentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create test-mode payment intent with idempotency support"
)
def create_payment_intent(req: PaymentIntentRequest):
    """
    Simulates Stripe/Razorpay Payment Intent creation in test-mode.
    Supports idempotency keys to prevent duplicate transaction charges.
    """
    # Check idempotency
    if req.idempotency_key and req.idempotency_key in payment_intents:
        cached = payment_intents[req.idempotency_key]
        logger.info(
            "PAYMENT_IDEMPOTENCY_HIT",
            f"Payment intent idempotency cache hit for key {req.idempotency_key}"
        )
        return PaymentIntentResponse(**cached)

    intent_id = f"pi_test_{uuid.uuid4().hex[:16]}"
    client_secret = f"{intent_id}_secret_{uuid.uuid4().hex[:16]}"
    now_ts = int(time.time())

    intent_data = {
        "id": intent_id,
        "client_secret": client_secret,
        "order_id": req.order_id,
        "amount": req.amount,
        "currency": req.currency.lower(),
        "status": "requires_payment_method",
        "mode": "test",
        "created_at": now_ts,
        "customer_email": req.customer_email
    }

    if req.idempotency_key:
        payment_intents[req.idempotency_key] = intent_data
    payment_intents[intent_id] = intent_data

    logger.info(
        "PAYMENT_INTENT_CREATED",
        f"Created test payment intent {intent_id} for order {req.order_id} (${req.amount})",
        metadata={"order_id": req.order_id, "amount": req.amount}
    )

    return PaymentIntentResponse(**intent_data)

@app.post(
    "/checkout/webhook/payment",
    status_code=status.HTTP_200_OK,
    summary="Signature-verified payment gateway webhook receiver"
)
async def payment_webhook(
    request: Request,
    x_signature: Optional[str] = Header(None, alias="X-Signature"),
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature")
):
    """
    Payment Gateway Signature-Verified Webhook:
    Enforces HMAC-SHA256 signature verification using PAYMENT_WEBHOOK_SECRET.
    Guarantees authenticity, rejects forged payloads, and processes status events idempotently.
    """
    signature = x_signature or stripe_signature
    if not signature:
        logger.warn("WEBHOOK_REJECTED", "Missing required signature header (X-Signature / Stripe-Signature)", status_code=401)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing signature header for payment webhook"
        )

    raw_body = await request.body()
    computed_sig = hmac.new(
        PAYMENT_WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).hexdigest()

    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(signature.strip(), computed_sig):
        logger.error(
            "WEBHOOK_SIGNATURE_MISMATCH",
            "Cryptographic webhook signature verification failed!",
            status_code=403
        )
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
    event_data = event.get("data", {}).get("object", {})
    intent_id = event_data.get("id")
    order_id = event_data.get("order_id")

    logger.info(
        "WEBHOOK_EVENT_VERIFIED",
        f"Verified payment webhook event: {event_type} for intent {intent_id}",
        metadata={"event_type": event_type, "intent_id": intent_id}
    )

    # Idempotent state transitions
    if event_type == "payment_intent.succeeded":
        if intent_id and intent_id in payment_intents:
            payment_intents[intent_id]["status"] = "succeeded"
        if order_id:
            order = db.orders.get(order_id)
            if order:
                order["status"] = "CONFIRMED_PAID"
                order["payment_status"] = "PAID"
                order["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    elif event_type == "payment_intent.payment_failed":
        if intent_id and intent_id in payment_intents:
            payment_intents[intent_id]["status"] = "failed"
        if order_id:
            order = db.orders.get(order_id)
            if order:
                order["status"] = "PAYMENT_FAILED"
                order["payment_status"] = "FAILED"

    return {
        "received": True,
        "event_type": event_type,
        "intent_id": intent_id,
        "signature_verified": True,
        "processed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

@app.get(
    "/checkout/payment-intents/{intent_id}",
    response_model=PaymentIntentResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve payment intent details"
)
def get_payment_intent(intent_id: str):
    if intent_id not in payment_intents:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment intent not found")
    return PaymentIntentResponse(**payment_intents[intent_id])

