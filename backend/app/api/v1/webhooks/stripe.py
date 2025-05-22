# backend/app/api/v1/webhooks/stripe.py
import logging
from fastapi import APIRouter, Request, Header, HTTPException, status, Depends
from typing import Any, Dict, Optional as TypingOptional # Renamed to avoid conflict with pydantic Optional
import stripe
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase # For type hinting the DB

from app.core.config import settings
# Adjust the import path for your CRUD operations for teachers
from app.db.crud import teacher as crud_teacher
# Import your actual database dependency function
from app.db.database import get_database # Assuming this is your DB dependency function
from app.models.teacher import TeacherUpdate, Teacher as TeacherModel # Your Teacher Pydantic models
from app.models.enums import SubscriptionPlan, StripeSubscriptionStatus # Your enums

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post(
    "/stripe", # This path should match the URL you configured in your Stripe Dashboard
    include_in_schema=False, # Typically, webhooks are not part of the public API schema
    summary="Stripe Webhook Handler",
    tags=["Webhooks"]
)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
    db: AsyncIOMotorDatabase = Depends(get_database) # Use your actual DB dependency
):
    """
    Handles incoming webhook events from Stripe.
    Verifies the event signature and processes relevant events to update the application's state.
    """
    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.error("CRITICAL: STRIPE_WEBHOOK_SECRET is not configured. Cannot process Stripe webhooks.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret not configured."
        )

    if stripe_signature is None:
        logger.warning("Stripe-Signature header missing from webhook request.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Stripe-Signature header.")

    try:
        payload = await request.body()
        event = stripe.Webhook.construct_event(
            payload, sig_header=stripe_signature, secret=settings.STRIPE_WEBHOOK_SECRET
        )
        logger.info(f"Stripe webhook event received: id={event.id}, type={event.type}")
    except ValueError as e:
        logger.error(f"Error parsing webhook payload: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid payload: {e}")
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Stripe signature verification failed: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid signature: {e}")
    except Exception as e:
        logger.error(f"Unexpected error constructing Stripe event: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error constructing event: {e}")

    event_data = event.data.object
    event_type = event.type

    # Helper function to update teacher and log
    async def _update_teacher_record(stripe_customer_id_to_find: str, update_payload: Dict[str, Any], event_details: str):
        logger.info(f"Attempting to update teacher for Stripe Customer {stripe_customer_id_to_find} due to {event_details} with data: {update_payload}")
        try:
            # Ensure your CRUD function can handle a Pydantic model or a dict
            # The TeacherUpdate model expects all fields to be optional.
            teacher_update_obj = TeacherUpdate(**update_payload)
            
            # You need a CRUD function like this:
            # async def update_teacher_by_stripe_customer_id(db: AsyncIOMotorDatabase, stripe_customer_id: str, data_to_update: TeacherUpdate) -> TypingOptional[TeacherModel]:
            updated_teacher = await crud_teacher.update_teacher_by_stripe_customer_id(
                db=db, 
                stripe_customer_id=stripe_customer_id_to_find, 
                data_to_update=teacher_update_obj
            )
            if updated_teacher:
                logger.info(f"Successfully updated teacher (Kinde ID: {updated_teacher.kinde_id}) for Stripe Customer {stripe_customer_id_to_find} due to {event_details}.")
            else:
                logger.warning(f"Teacher not found or not updated for Stripe Customer {stripe_customer_id_to_find} during {event_details}.")
        except Exception as db_exc:
            logger.error(f"Database error updating teacher for Stripe Customer {stripe_customer_id_to_find} ({event_details}): {db_exc}", exc_info=True)


    try:
        if event_type == 'checkout.session.completed':
            logger.info(f"Handling checkout.session.completed for session: {event_data.id}")
            stripe_customer_id = event_data.get("customer")
            stripe_subscription_id = event_data.get("subscription")

            if not stripe_customer_id or not stripe_subscription_id:
                logger.error(f"Missing customer or subscription ID in checkout.session.completed: {event_data.id}")
                return {"status": "error", "message": "Missing customer/subscription ID in event"}

            try:
                subscription = stripe.Subscription.retrieve(stripe_subscription_id)
                current_period_end_ts = subscription.current_period_end
                current_period_end_dt = datetime.fromtimestamp(current_period_end_ts, tz=timezone.utc)
                plan_id_from_stripe = subscription.items.data[0].price.id if subscription.items.data else None
                
                update_data = {
                    "stripe_subscription_id": stripe_subscription_id,
                    "subscription_status": StripeSubscriptionStatus.ACTIVE,
                    "current_period_end": current_period_end_dt,
                }
                if plan_id_from_stripe == settings.STRIPE_PRO_PLAN_PRICE_ID:
                    update_data["current_plan"] = SubscriptionPlan.PRO
                else:
                    logger.warning(f"Subscription {stripe_subscription_id} created with unexpected plan ID {plan_id_from_stripe} vs expected {settings.STRIPE_PRO_PLAN_PRICE_ID}")

                await _update_teacher_record(stripe_customer_id, update_data, "checkout.session.completed")

            except stripe.error.StripeError as se:
                logger.error(f"Stripe error retrieving subscription {stripe_subscription_id} for checkout.session.completed: {se}", exc_info=True)
            except Exception as e_sub:
                logger.error(f"Error processing subscription details for {stripe_subscription_id} (checkout.session.completed): {e_sub}", exc_info=True)

        elif event_type == 'invoice.paid':
            logger.info(f"Handling invoice.paid for invoice: {event_data.id}")
            stripe_customer_id = event_data.get("customer")
            stripe_subscription_id = event_data.get("subscription") # This should be present for subscription invoices
            billing_reason = event_data.get("billing_reason")

            if not stripe_customer_id or not stripe_subscription_id:
                logger.error(f"Missing customer or subscription ID in invoice.paid: {event_data.id}")
                return {"status": "error", "message": "Missing customer/subscription ID in event"}

            if billing_reason in ['subscription_cycle', 'subscription_create', 'subscription_update']:
                current_period_end_ts = event_data.get("period_end")
                if not current_period_end_ts and event_data.lines and event_data.lines.data:
                    line_item_period = event_data.lines.data[0].period
                    current_period_end_ts = line_item_period.end

                if current_period_end_ts:
                    current_period_end_dt = datetime.fromtimestamp(current_period_end_ts, tz=timezone.utc)
                    update_data = {
                        "subscription_status": StripeSubscriptionStatus.ACTIVE,
                        "current_period_end": current_period_end_dt,
                        "current_plan": SubscriptionPlan.PRO # Reinforce Pro plan status
                    }
                    await _update_teacher_record(stripe_customer_id, update_data, f"invoice.paid ({billing_reason})")
                else:
                    logger.warning(f"Could not determine current_period_end from invoice.paid event: {event_data.id}")
            else:
                logger.info(f"invoice.paid event with billing_reason '{billing_reason}' not processed for subscription update for invoice {event_data.id}.")

        elif event_type == 'invoice.payment_failed':
            logger.info(f"Handling invoice.payment_failed for invoice: {event_data.id}")
            stripe_customer_id = event_data.get("customer")
            # stripe_subscription_id = event_data.get("subscription") # May not always be present

            if not stripe_customer_id:
                logger.error(f"Missing customer ID in invoice.payment_failed: {event_data.id}")
                return {"status": "error", "message": "Missing customer ID in event"}
            
            # It's better to fetch the subscription to get its actual status from Stripe
            # as Stripe's dunning process might change it (e.g., to past_due, then unpaid).
            # For simplicity here, we'll set it to PAST_DUE, but a more robust solution
            # would fetch the subscription linked to this customer/invoice.
            update_data = {"subscription_status": StripeSubscriptionStatus.PAST_DUE}
            await _update_teacher_record(stripe_customer_id, update_data, "invoice.payment_failed")
            # Consider sending a notification to the user.

        elif event_type == 'customer.subscription.updated':
            logger.info(f"Handling customer.subscription.updated for subscription: {event_data.id}")
            stripe_customer_id = event_data.get("customer")
            stripe_subscription_id = event_data.id
            new_status_str = event_data.get("status")
            current_period_end_ts = event_data.get("current_period_end")
            cancel_at_period_end = event_data.get("cancel_at_period_end", False)

            if not stripe_customer_id:
                logger.error(f"Missing customer ID in customer.subscription.updated: {event_data.id}")
                return {"status": "error", "message": "Missing customer ID in event"}

            update_data_payload: Dict[str, Any] = {}
            try:
                if new_status_str:
                    update_data_payload["subscription_status"] = StripeSubscriptionStatus(new_status_str)
            except ValueError:
                logger.warning(f"Unknown subscription status '{new_status_str}' received from Stripe for sub {stripe_subscription_id}.")
            
            if current_period_end_ts:
                update_data_payload["current_period_end"] = datetime.fromtimestamp(current_period_end_ts, tz=timezone.utc)
            
            # If subscription is active but scheduled for cancellation, status is still 'active'
            # but cancel_at_period_end is true. 'customer.subscription.deleted' will handle final plan change.
            if new_status_str == StripeSubscriptionStatus.ACTIVE.value and cancel_at_period_end:
                 logger.info(f"Subscription {stripe_subscription_id} is active and scheduled to cancel at period end.")
                 # You might add a custom status in your DB like "active_pending_cancellation" if needed
                 # For now, we just update status and period_end.

            if update_data_payload:
                await _update_teacher_record(stripe_customer_id, update_data_payload, "customer.subscription.updated")

        elif event_type == 'customer.subscription.deleted':
            logger.info(f"Handling customer.subscription.deleted for subscription: {event_data.id}")
            stripe_customer_id = event_data.get("customer")

            if not stripe_customer_id:
                logger.error(f"Missing customer ID in customer.subscription.deleted: {event_data.id}")
                return {"status": "error", "message": "Missing customer ID in event"}

            update_data = {
                "current_plan": SubscriptionPlan.FREE,
                "subscription_status": StripeSubscriptionStatus.CANCELED, # Mark as canceled
                "stripe_subscription_id": None, # Clear the Stripe subscription ID
                "current_period_end": None,     # Clear the period end
            }
            await _update_teacher_record(stripe_customer_id, update_data, "customer.subscription.deleted")

        else:
            logger.info(f"Unhandled Stripe event type: {event_type} (ID: {event.id})")

    except Exception as e_handler:
        logger.error(f"Error handling Stripe event {event_type} (ID: {event.id}): {e_handler}", exc_info=True)
        return {"status": "error", "message": "Internal server error processing webhook event."}

    return {"status": "success", "message": f"Webhook event {event.id} received."}
