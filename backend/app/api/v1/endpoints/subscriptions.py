# backend/app/api/v1/endpoints/subscriptions.py
import logging
import os
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import stripe # Stripe library for payment processing
from motor.motor_asyncio import AsyncIOMotorDatabase # For type hinting DB if needed

# Adjusted import paths to be relative to the current file's location (endpoints/subscriptions.py)
from ....core.config import settings # Your application settings
from ....db import crud # Your CRUD operations
from ....models.teacher import Teacher, TeacherUpdate # Teacher Pydantic model
from ...deps import get_current_teacher # Kinde auth dependency
from ....db.database import get_database # Import your database dependency function

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Pydantic Models ---
class CheckoutSessionResponse(BaseModel):
    """
    Response model for the create_checkout_session endpoint.
    Contains the ID of the Stripe Checkout Session.
    """
    sessionId: str

class PortalSessionResponse(BaseModel):
    """
    Response model for the create_portal_session endpoint.
    Contains the URL to redirect the user to the Stripe Customer Portal.
    """
    url: str

class CreateCheckoutSessionRequest(BaseModel):
    """
    Request model for creating a checkout session.
    """
    pass


# --- API Endpoint ---
@router.post(
    "/create-checkout-session",
    response_model=CheckoutSessionResponse,
    summary="Create a Stripe Checkout Session for Pro Plan Subscription",
    tags=["Subscriptions - Stripe"]
)
async def create_checkout_session(
    *,
    current_teacher: Teacher = Depends(get_current_teacher),
    db: AsyncIOMotorDatabase = Depends(get_database) # Inject DB session for CRUD operations
):
    """
    Creates a Stripe Checkout Session to allow the currently authenticated teacher
    to subscribe to the Pro plan.

    - Retrieves or creates a Stripe Customer for the teacher.
    - Updates the teacher's record with the Stripe Customer ID.
    - Creates a Checkout Session with the Pro plan Price ID from settings.
    - Returns the Checkout Session ID to the frontend.
    """
    if not settings.STRIPE_PRO_PLAN_PRICE_ID:
        logger.error("STRIPE_PRO_PLAN_PRICE_ID is not configured in settings.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error: Pro plan ID is missing."
        )

    if not settings.STRIPE_SECRET_KEY:
        logger.error("STRIPE_SECRET_KEY is not configured.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error: Stripe secret key is missing."
        )

    stripe_customer_id = current_teacher.stripe_customer_id

    try:
        if not stripe_customer_id:
            logger.info(f"No Stripe Customer ID found for teacher {current_teacher.kinde_id}. Creating a new Stripe Customer.")
            customer_params = {
                "email": current_teacher.email,
                "name": f"{current_teacher.first_name} {current_teacher.last_name}",
                "metadata": {
                    "teacher_internal_id": str(current_teacher.id),
                    "teacher_kinde_id": current_teacher.kinde_id,
                }
            }
            stripe_customer = stripe.Customer.create(**customer_params)
            stripe_customer_id = stripe_customer.id
            logger.info(f"Created Stripe Customer {stripe_customer_id} for teacher {current_teacher.kinde_id}.")

            # Update the teacher record in your database with the new stripe_customer_id
            updated_teacher_data_payload = {"stripe_customer_id": stripe_customer_id}
            teacher_update_model = TeacherUpdate(**updated_teacher_data_payload)
            
            try:
                # Using crud.update_teacher which takes kinde_id and TeacherUpdate model
                # The 'db' parameter is not explicitly used by your crud.update_teacher
                # as it calls _get_collection internally, which calls get_database().
                # However, passing it for consistency if other CRUDs need it or if internal logic changes.
                # The @with_transaction decorator in your crud.py will handle session if needed.
                updated_teacher_db_record = await crud.update_teacher(
                    kinde_id=current_teacher.kinde_id,
                    teacher_in=teacher_update_model
                    # session=db # Not passing db as session, as crud.update_teacher expects Motor session or None
                )
                if updated_teacher_db_record:
                    logger.info(f"Successfully updated teacher {current_teacher.kinde_id} with Stripe Customer ID {stripe_customer_id}.")
                else:
                    logger.error(f"Failed to update teacher {current_teacher.kinde_id} in DB with Stripe Customer ID {stripe_customer_id}. CRUD function returned None.")
                    # This is a critical failure; the Stripe customer was created but not linked.
                    # Consider how to handle this: retry, manual reconciliation flag, etc.
                    # For now, we'll raise an error to prevent proceeding with an unlinked customer.
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to link Stripe customer to teacher account."
                    )
            except Exception as db_exc:
                logger.error(f"Database error updating teacher {current_teacher.kinde_id} with Stripe Customer ID: {db_exc}", exc_info=True)
                # This is also a critical failure.
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Database error while linking Stripe customer."
                )

        frontend_base_url = settings.FRONTEND_URL or os.getenv("FRONTEND_URL", "http://localhost:5173")
        
        success_url = f"{frontend_base_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{frontend_base_url}/payment/canceled"

        logger.info(f"Creating Stripe Checkout Session for customer {stripe_customer_id} with Pro Plan Price ID {settings.STRIPE_PRO_PLAN_PRICE_ID}.")
        logger.info(f"Success URL: {success_url}, Cancel URL: {cancel_url}")

        checkout_session_params = {
            "customer": stripe_customer_id,
            "payment_method_types": ['card'],
            "line_items": [
                {
                    "price": settings.STRIPE_PRO_PLAN_PRICE_ID,
                    "quantity": 1,
                }
            ],
            "mode": 'subscription',
            "success_url": success_url,
            "cancel_url": cancel_url,
        }
        checkout_session = stripe.checkout.Session.create(**checkout_session_params)
        logger.info(f"Stripe Checkout Session {checkout_session.id} created successfully.")

        return CheckoutSessionResponse(sessionId=checkout_session.id)

    except stripe.error.StripeError as e:
        logger.error(f"Stripe API error during checkout session creation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stripe error: {e.user_message or str(e)}"
        )
    except HTTPException: # Re-raise HTTPExceptions from DB update failure
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred during checkout session creation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the checkout session."
        )

@router.post(
    "/create-portal-session",
    response_model=PortalSessionResponse,
    summary="Create a Stripe Customer Portal Session",
    tags=["Subscriptions - Stripe"]
)
async def create_portal_session(
    current_teacher: Teacher = Depends(get_current_teacher)
):
    """
    Creates a Stripe Customer Billing Portal session for the currently
    authenticated teacher to manage their subscription.
    """
    if not current_teacher.stripe_customer_id:
        logger.warning(f"Teacher {current_teacher.kinde_id} attempted to access customer portal without a Stripe customer ID.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription found for this account. Please subscribe first."
        )

    frontend_base_url = settings.FRONTEND_URL or os.getenv("FRONTEND_URL", "http://localhost:5173")
    return_url = f"{frontend_base_url}/account/billing"

    try:
        logger.info(f"Creating Stripe Customer Portal session for customer {current_teacher.stripe_customer_id}. Return URL: {return_url}")
        portal_session = stripe.billing_portal.Session.create(
            customer=current_teacher.stripe_customer_id,
            return_url=return_url,
        )
        logger.info(f"Stripe Customer Portal session {portal_session.id} created successfully.")
        return PortalSessionResponse(url=portal_session.url)
    except stripe.error.StripeError as e:
        logger.error(f"Stripe API error creating portal session for customer {current_teacher.stripe_customer_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stripe error: {e.user_message or str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error creating portal session for customer {current_teacher.stripe_customer_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the customer portal session."
        )
