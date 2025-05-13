# app/api/v1/webhooks/kinde.py

import logging
from typing import Dict, Any
from fastapi import APIRouter, Request, HTTPException, status, Header
import hmac
import hashlib
import os # For environment variable

# Import CRUD function and necessary model
from ....db import crud
from ....models.teacher import TeacherCreateInternal # Model for data from Kinde

# Setup logger
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/webhooks/kinde",
    tags=["Webhooks"],
    # include_in_schema=False # Hide from public API docs
)

# --- Kinde Webhook Secret Verification (Optional but Recommended) ---
# Store your Kinde webhook secret securely, e.g., in environment variables
KINDE_WEBHOOK_SECRET = os.getenv("KINDE_WEBHOOK_SECRET")

async def verify_kinde_signature(request: Request, kinde_signature: Optional[str] = Header(None)):
    """Dependency to verify the Kinde webhook signature."""
    if not KINDE_WEBHOOK_SECRET:
        logger.warning("KINDE_WEBHOOK_SECRET not configured. Skipping signature verification.")
        # In production, you might want to raise an error if the secret is missing
        # raise HTTPException(status_code=500, detail="Webhook secret not configured")
        return # Allow request if secret is not set (for testing maybe)

    if not kinde_signature:
        logger.error("Missing Kinde-Signature header")
        raise HTTPException(status_code=400, detail="Missing Kinde-Signature header")

    try:
        raw_body = await request.body()
        # Kinde signature is typically 't=<timestamp>,v1=<signature>'
        # You need to extract the signature part and verify it
        # Example using HMAC-SHA256 (confirm Kinde's exact algorithm)
        parts = {p.split('=')[0]: p.split('=')[1] for p in kinde_signature.split(',')}
        timestamp = parts.get('t')
        signature = parts.get('v1')

        if not timestamp or not signature:
             raise ValueError("Invalid signature header format")

        signed_payload = f"{timestamp}.{raw_body.decode()}".encode('utf-8')
        expected_signature = hmac.new(
            KINDE_WEBHOOK_SECRET.encode('utf-8'),
            signed_payload,
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected_signature, signature):
            logger.error("Invalid Kinde webhook signature.")
            raise HTTPException(status_code=403, detail="Invalid signature")

        logger.info("Kinde webhook signature verified successfully.")

    except Exception as e:
        logger.error(f"Error verifying Kinde signature: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Webhook signature verification failed")


# --- Webhook Endpoint for User Creation ---
@router.post(
    "/user-created",
    status_code=status.HTTP_204_NO_CONTENT, # Return 204 on success
    summary="Handle Kinde User Created Webhook",
    description="Receives user creation events from Kinde and creates corresponding teacher profile.",
    # dependencies=[Depends(verify_kinde_signature)] # Uncomment to enable signature verification
)
async def handle_user_created_webhook(payload: Dict[str, Any]):
    """
    Handles the 'user.created' event from Kinde.
    """
    logger.info("Received Kinde webhook payload.")
    logger.debug(f"Webhook payload: {payload}")

    event_type = payload.get("type")

    # Ensure it's the correct event type
    if event_type != "user.created":
        logger.warning(f"Received unexpected webhook event type: {event_type}")
        # Return success to Kinde even if it's not the event we handle here
        return

    # Extract necessary data from the 'data' part of the payload
    user_data = payload.get("data", {}).get("user", {})
    kinde_id = user_data.get("id") # This is the 'sub' claim
    email = user_data.get("email")
    first_name = user_data.get("first_name")
    last_name = user_data.get("last_name")

    if not kinde_id or not email:
        logger.error(f"Webhook payload missing required fields: kinde_id={kinde_id}, email={email}")
        # Still return success to Kinde to prevent retries, but log the error
        return

    logger.info(f"Processing user.created event for Kinde ID: {kinde_id}, Email: {email}")

    # Prepare data for teacher creation using the internal model
    try:
        teacher_data_internal = TeacherCreateInternal(
            kinde_id=kinde_id,
            email=email,
            first_name=first_name,
            last_name=last_name
        )
    except ValidationError as e:
         logger.error(f"Failed to validate data from Kinde webhook for {kinde_id}: {e.errors()}")
         # Return success to Kinde, but log error
         return

    # Check if teacher already exists (should ideally not happen for user.created, but good safeguard)
    existing_teacher = await crud.get_teacher_by_kinde_id(kinde_id=kinde_id)
    if existing_teacher:
        logger.warning(f"Teacher profile already exists for Kinde ID {kinde_id} during user.created webhook processing.")
        # Return success as the desired state (user exists) is achieved
        return

    # Create the teacher record in the database
    try:
        # Use the specific internal creation model
        created_teacher = await crud.create_teacher(teacher_in=teacher_data_internal)
        if created_teacher:
            logger.info(f"Successfully created teacher profile via webhook for Kinde ID: {kinde_id}, Internal ID: {created_teacher.id}")
        else:
            # This indicates a DB error during creation
            logger.error(f"crud.create_teacher failed for webhook event, Kinde ID: {kinde_id}")
            # Don't raise HTTPException here, as Kinde might retry indefinitely on failure.
            # Log the error thoroughly for investigation.
    except Exception as e:
        logger.error(f"Exception during crud.create_teacher for webhook event, Kinde ID: {kinde_id}: {e}", exc_info=True)
        # Don't raise HTTPException

    # Return No Content to Kinde to acknowledge receipt
    return

