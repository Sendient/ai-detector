# backend/app/api/v1/webhooks/stripe.py
import logging
from fastapi import APIRouter, Request, Header, HTTPException, status, Depends
from typing import Any, Dict, Optional as TypingOptional # Renamed to avoid conflict with pydantic Optional
import stripe
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase # For type hinting the DB

from ....core.config import settings
from ....db import crud as crud_teacher # crud.py contains teacher-related functions
from ....db.database import get_database
from ....models.teacher import TeacherUpdate, Teacher as TeacherModel
from ....models.enums import SubscriptionPlan, StripeSubscriptionStatus

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
    logger.info(f"ENTERED STRIPE WEBHOOK HANDLER. Value of settings.STRIPE_WEBHOOK_SECRET: '{settings.STRIPE_WEBHOOK_SECRET}'")

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
                # Expand necessary fields to ensure they are populated
                logger.info(f"Retrieving subscription {stripe_subscription_id} with expansion for items.data.price and items.data.plan.")
                subscription = stripe.Subscription.retrieve(
                    stripe_subscription_id,
                    expand=['items.data.price', 'items.data.plan'] # Ensure price and plan details are expanded
                )
                
                logger.info(f"Retrieved subscription object for {stripe_subscription_id}.")
                try:
                    # Log structure as seen by Python Stripe library
                    sub_dict = subscription.to_dict_recursive()
                    logger.debug(f"Subscription object for {stripe_subscription_id} (recursive dict): {sub_dict}")
                    items_from_dict = sub_dict.get('items', {}).get('data', [])
                    logger.debug(f"Items from dict for {stripe_subscription_id}: {items_from_dict}")
                    top_level_cpe_from_dict = sub_dict.get('current_period_end')
                    logger.debug(f"Top-level current_period_end from dict for {stripe_subscription_id}: {top_level_cpe_from_dict}")
                except Exception as e_log_struct:
                    logger.warning(f"Could not log subscription structure as dict for {stripe_subscription_id}: {e_log_struct}")

                current_period_end_ts = None
                plan_id_from_stripe = None

                # Attempt 1: Access through the dictionary representation (more reliable given logs)
                try:
                    sub_dict = subscription.to_dict_recursive() # Already logged above, re-access for clarity
                    logger.info(f"Attempting to access data from subscription_dict for {stripe_subscription_id}")
                    
                    items_data = sub_dict.get('items', {}).get('data', [])
                    if items_data:
                        subscription_item_dict = items_data[0]
                        current_period_end_ts = subscription_item_dict.get('current_period_end')
                        price_dict = subscription_item_dict.get('price', {})
                        plan_id_from_stripe = price_dict.get('id')
                        logger.info(f"From dict access on items: current_period_end_ts={current_period_end_ts}, plan_id_from_stripe={plan_id_from_stripe}")
                    else:
                        logger.warning(f"items.data was empty or not found in subscription_dict for {stripe_subscription_id}. Dict items: {sub_dict.get('items')}")
                except Exception as e_dict_access:
                    logger.error(f"Error accessing data via dict for {stripe_subscription_id}: {e_dict_access}", exc_info=True)

                # Attempt 2: Fallback to direct attribute access if dict access somehow failed (less likely now)
                if current_period_end_ts is None or plan_id_from_stripe is None:
                    logger.warning(f"Dict access failed for {stripe_subscription_id} (cpe_ts: {current_period_end_ts}, plan_id: {plan_id_from_stripe}). Attempting direct attribute access as fallback.")
                    try:
                        if subscription.items and hasattr(subscription.items, 'data') and subscription.items.data:
                            subscription_item = subscription.items.data[0]
                            if current_period_end_ts is None: # Only overwrite if not found from dict
                                current_period_end_ts = subscription_item.current_period_end
                            if plan_id_from_stripe is None: # Only overwrite if not found from dict
                                if hasattr(subscription_item, 'price') and subscription_item.price and hasattr(subscription_item.price, 'id'):
                                    plan_id_from_stripe = subscription_item.price.id
                            logger.info(f"From fallback attribute access: current_period_end_ts={current_period_end_ts}, plan_id_from_stripe={plan_id_from_stripe}")
                        else:
                            logger.warning(f"Fallback attribute access: subscription.items.data was not valid or empty for {stripe_subscription_id}.")
                    except Exception as e_attr_fallback:
                        logger.error(f"Error during fallback attribute access for {stripe_subscription_id}: {e_attr_fallback}", exc_info=True)

                # Attempt 3: Deep fallback for current_period_end to top-level object if still not found
                if current_period_end_ts is None:
                    logger.warning(f"current_period_end_ts is still None for {stripe_subscription_id}. Attempting deep fallback to subscription.current_period_end (attribute). REMOVE IF UNNECESSARY")
                    try:
                        current_period_end_ts = subscription.current_period_end # Direct attribute on main object
                        logger.info(f"Deep fallback to subscription.current_period_end (attribute) yielded: {current_period_end_ts}")
                    except AttributeError:
                        logger.error(f"AttributeError on deep fallback subscription.current_period_end (attribute) for {stripe_subscription_id}.")
                    except Exception as e_deep_fallback_cpe:
                         logger.error(f"Unexpected error on deep fallback subscription.current_period_end (attribute) for {stripe_subscription_id}: {e_deep_fallback_cpe}", exc_info=True)

                # Fallback for plan_id using subscription.plan.id if it's still None
                if plan_id_from_stripe is None:
                    logger.warning(f"plan_id_from_stripe is still None for {stripe_subscription_id}. Checking subscription.plan.id (attribute) as final fallback.")
                    try:
                        if hasattr(subscription, 'plan') and subscription.plan and hasattr(subscription.plan, 'id'):
                            plan_id_from_stripe = subscription.plan.id
                            logger.info(f"Final fallback to subscription.plan.id (attribute) yielded: {plan_id_from_stripe}")
                        else:
                            logger.warning(f"subscription.plan or subscription.plan.id not found on attribute fallback for {stripe_subscription_id}.")
                    except Exception as e_final_fallback_plan:
                         logger.error(f"Unexpected error on final fallback subscription.plan.id (attribute) for {stripe_subscription_id}: {e_final_fallback_plan}", exc_info=True)
                
                if current_period_end_ts is None:
                    logger.critical(f"CRITICAL FAILURE: current_period_end_ts is STILL None for {stripe_subscription_id} after all attempts. Cannot process this event properly.")
                    return {"status": "error", "message": "Critical: Could not determine subscription period end after all attempts."}

                current_period_end_dt = datetime.fromtimestamp(current_period_end_ts, tz=timezone.utc)
                
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
                logger.error(f"Stripe error retrieving or processing subscription {stripe_subscription_id} for checkout.session.completed: {se}", exc_info=True)
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

        elif event_type == 'customer.subscription.created':
            logger.info(f"Handling customer.subscription.created for subscription: {event_data.id}")
            stripe_customer_id = event_data.get("customer")
            stripe_subscription_id = event_data.id # The event_data is the subscription object
            subscription_status_str = event_data.get("status")
            current_period_end_ts = event_data.get("current_period_end")
            plan_data = event_data.get("items", {}).get("data", [])
            plan_id_from_stripe = plan_data[0].get("price", {}).get("id") if plan_data else None

            if not stripe_customer_id:
                logger.error(f"Missing customer ID in customer.subscription.created: {event_data.id}")
                return {"status": "error", "message": "Missing customer ID in event"}

            update_data: Dict[str, Any] = {
                "stripe_subscription_id": stripe_subscription_id,
            }

            try:
                if subscription_status_str:
                    update_data["subscription_status"] = StripeSubscriptionStatus(subscription_status_str)
            except ValueError:
                logger.warning(f"Unknown subscription status '{subscription_status_str}' received from Stripe for sub {stripe_subscription_id} (customer.subscription.created).")

            if current_period_end_ts:
                update_data["current_period_end"] = datetime.fromtimestamp(current_period_end_ts, tz=timezone.utc)

            if plan_id_from_stripe == settings.STRIPE_PRO_PLAN_PRICE_ID:
                update_data["current_plan"] = SubscriptionPlan.PRO
            elif plan_id_from_stripe: # It's a different plan
                logger.warning(f"Subscription {stripe_subscription_id} (customer.subscription.created) has unexpected plan ID {plan_id_from_stripe} vs expected {settings.STRIPE_PRO_PLAN_PRICE_ID}. Setting plan to FREE or NONE based on your logic.")
                # Decide if you want to set to FREE or leave as is / set to another status
                update_data["current_plan"] = SubscriptionPlan.FREE # Example: Downgrade if plan is unknown
            
            if update_data: # Only update if there's something to update
                 await _update_teacher_record(stripe_customer_id, update_data, "customer.subscription.created")

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

        # --- Start of new logging-only handlers ---
        elif event_type == 'customer.created':
            logger.info(f"Webhook received: {event_type} for customer {event_data.id}. Customer creation is primarily handled during checkout session initiation or by customer.subscription.created.")
        
        elif event_type == 'charge.succeeded':
            logger.info(f"Webhook received: {event_type} for charge {event_data.id}. Relevant subscription updates are handled by invoice events (e.g. invoice.paid).")

        elif event_type == 'payment_method.attached':
            customer_id = event_data.get("customer", "N/A")
            logger.info(f"Webhook received: {event_type} for customer {customer_id}, payment_method {event_data.id}.")

        elif event_type == 'payment_intent.created':
            logger.info(f"Webhook received: {event_type} for payment_intent {event_data.id}.")

        elif event_type == 'payment_intent.succeeded':
            logger.info(f"Webhook received: {event_type} for payment_intent {event_data.id}. Relevant subscription updates are handled by invoice events.")

        elif event_type == 'invoice.created':
            logger.info(f"Webhook received: {event_type} for invoice {event_data.id}. Awaiting payment confirmation (e.g., via invoice.paid).")

        elif event_type == 'invoice.finalized':
            logger.info(f"Webhook received: {event_type} for invoice {event_data.id}. Awaiting payment confirmation (e.g., via invoice.paid).")
            
        elif event_type == 'invoice.payment_succeeded':
            logger.info(f"Webhook received: {event_type} for invoice {event_data.id}. Core logic typically handled by invoice.paid.")
        # --- End of new logging-only handlers ---

        else:
            logger.info(f"Unhandled Stripe event type: {event_type} (ID: {event.id})")

    except Exception as e_handler:
        logger.error(f"Error handling Stripe event {event_type} (ID: {event.id}): {e_handler}", exc_info=True)
        return {"status": "error", "message": "Internal server error processing webhook event."}

    return {"status": "success", "message": f"Webhook event {event.id} received."}
