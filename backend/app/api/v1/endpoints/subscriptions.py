# backend/app/api/v1/endpoints/subscriptions.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import stripe # Import the stripe library

from app.core.config import settings # Your application settings
from app.models.teacher import Teacher # Your Teacher Pydantic model
from app.api.deps import get_current_active_teacher # Your Kinde auth dependency
from app.db import crud # Assuming you have CRUD operations for teachers

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Pydantic Models ---
class CheckoutSessionResponse(BaseModel):
    """
    Response model for the create_checkout_session endpoint.
    Contains the ID of the Stripe Checkout Session.
    """
    sessionId: str # Using sessionId to match common frontend conventions (Stripe.js uses camelCase)

class CreateCheckoutSessionRequest(BaseModel):
    """
    Request model for creating a checkout session.
    price_id: The ID of the Stripe Price object for the plan to subscribe to.
    """
    # For now, we'll hardcode the Pro Plan Price ID from settings,
    # but if you want to support multiple plans via this endpoint later,
    # you might pass a price_id or plan_identifier in the request.
    # For this iteration, no request body is strictly needed if it's always the Pro plan.
    pass


# --- API Endpoint ---
@router.post(
    "/subscriptions/create-checkout-session",
    response_model=CheckoutSessionResponse,
    summary="Create a Stripe Checkout Session for Pro Plan Subscription",
    tags=["Subscriptions"]
)
async def create_checkout_session(
    *,
    # request_data: CreateCheckoutSessionRequest, # Uncomment if you decide to pass price_id in request
    current_teacher: Teacher = Depends(get_current_active_teacher) # Kinde authenticated teacher
):
    """
    Creates a Stripe Checkout Session to allow the currently authenticated teacher
    to subscribe to the Pro plan.

    - Retrieves or creates a Stripe Customer for the teacher.
    - Creates a Checkout Session with the Pro plan Price ID from settings.
    - Returns the Checkout Session ID to the frontend.
    """
    if not settings.STRIPE_PRO_PLAN_PRICE_ID:
        logger.error("STRIPE_PRO_PLAN_PRICE_ID is not configured in settings.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error: Pro plan ID is missing."
        )

    if not settings.STRIPE_SECRET_KEY: # Should have been caught at startup, but good to check
        logger.error("STRIPE_SECRET_KEY is not configured.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error: Stripe secret key is missing."
        )

    stripe_customer_id = current_teacher.stripe_customer_id

    try:
        if not stripe_customer_id:
            logger.info(f"No Stripe Customer ID found for teacher {current_teacher.kinde_id}. Creating a new Stripe Customer.")
            # Create a new Stripe Customer
            customer_params = {
                "email": current_teacher.email,
                "name": f"{current_teacher.first_name} {current_teacher.last_name}",
                "metadata": {
                    "teacher_internal_id": str(current_teacher.id), # Your MongoDB Teacher _id
                    "teacher_kinde_id": current_teacher.kinde_id,
                }
            }
            stripe_customer = stripe.Customer.create(**customer_params)
            stripe_customer_id = stripe_customer.id
            logger.info(f"Created Stripe Customer {stripe_customer_id} for teacher {current_teacher.kinde_id}.")

            # Update the teacher record in your database with the new stripe_customer_id
            updated_teacher_data = {"stripe_customer_id": stripe_customer_id}
            
            # Assuming crud.teacher.update can take the teacher object or its ID, and the update data
            # You might need to adjust this based on your actual CRUD function signature
            # e.g., await crud.teacher.update(db, db_obj=current_teacher, obj_in=updated_teacher_data)
            # or await crud.teacher.update_teacher_by_kinde_id(kinde_id=current_teacher.kinde_id, update_data=updated_teacher_data)
            
            # For this example, let's assume a generic update method.
            # This part is CRITICAL and needs to match your actual DB update mechanism.
            # You'll need to inject your database session/client if crud operations require it.
            # For now, this is a placeholder for the database update logic.
            # IMPORTANT: Replace with your actual database update call
            try:
                # This is a conceptual placeholder. Your actual CRUD will look different.
                # You'll likely need access to your database client/session here.
                # This might involve adding a DB dependency to this endpoint.
                # For example: db: AsyncIOMotorClient = Depends(get_db_dependency)
                # await crud.teacher.update_by_kinde_id(db, kinde_id=current_teacher.kinde_id, obj_in=updated_teacher_data)
                logger.info(f"Attempting to update teacher {current_teacher.kinde_id} with Stripe Customer ID {stripe_customer_id}. (DB update logic placeholder)")
                # --- Placeholder for DB Update ---
                # Example if your CRUD takes a Pydantic model for update:
                # teacher_update_model = TeacherUpdate(**updated_teacher_data)
                # await crud.teacher.update(db_session_dependency, db_obj=current_teacher, obj_in=teacher_update_model)
                # --- End Placeholder ---
                # For now, we assume the update is successful for the flow.
                # In a real scenario, handle potential DB update failures.
                pass # Remove this pass when actual DB update is implemented
            except Exception as db_exc:
                logger.error(f"Failed to update teacher {current_teacher.kinde_id} with Stripe Customer ID: {db_exc}", exc_info=True)
                # Decide if you want to proceed if DB update fails. For now, we'll proceed but log.
                # In a robust system, you might want to roll back Stripe customer creation or retry.

        # Define success and cancel URLs (these should be routes in your React frontend)
        # Ensure these are absolute URLs
        # TODO: Get these from settings or construct them properly based on your frontend deployment
        frontend_base_url = os.getenv("FRONTEND_URL", "http://localhost:5173") # Get from env or default
        
        success_url = f"{frontend_base_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{frontend_base_url}/payment/canceled"

        logger.info(f"Creating Stripe Checkout Session for customer {stripe_customer_id} with Pro Plan Price ID {settings.STRIPE_PRO_PLAN_PRICE_ID}.")
        logger.info(f"Success URL: {success_url}, Cancel URL: {cancel_url}")

        # Create the Stripe Checkout Session
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
            # "automatic_tax": {"enabled": True}, # Optional: Enable automatic tax collection if configured
            # "allow_promotion_codes": True, # Optional: Allow promotion codes if you use them
        }
        checkout_session = stripe.checkout.Session.create(**checkout_session_params)
        logger.info(f"Stripe Checkout Session {checkout_session.id} created successfully.")

        return CheckoutSessionResponse(sessionId=checkout_session.id)

    except stripe.error.StripeError as e:
        logger.error(f"Stripe API error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stripe error: {e.user_message or str(e)}" # Provide user-friendly message if available
        )
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the checkout session."
        )

