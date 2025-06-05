import stripe
import os
from typing import Dict, Any, List, Optional
from fastapi import HTTPException, status, Request # Request is needed for webhook handling
import asyncio

from backend.app.core.config import settings # Assuming you have a settings module for config

# --- Stripe API Initialization ---
# It's crucial to set your Stripe API key.
# This should ideally come from an environment variable for security.
# Ensure STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET are set in your environment or .env file
stripe.api_key = settings.STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET = settings.STRIPE_WEBHOOK_SECRET # For verifying webhook signatures

# --- Helper Functions (Optional but good practice) ---

def get_base_url(request: Request) -> str:
    """
    Constructs the base URL from the request.
    Helpful for constructing success_url and cancel_url for Stripe Checkout.
    """
    # For local development, you might hardcode or use a setting.
    # For production, derive it from request headers or a configuration.
    # Example: return f"{request.url.scheme}://{request.url.netloc}"
    # Using a configured frontend URL is often more reliable
    return settings.FRONTEND_URL


# --- Core Stripe Service Functions ---

async def create_stripe_checkout_session(
    price_id: str,
    quantity: int = 1,
    customer_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None # Pass request if you need to construct URLs dynamically
) -> stripe.checkout.Session:
    """
    Creates a Stripe Checkout Session for a one-time payment or subscription.

    Args:
        price_id: The ID of the Stripe Price object.
        quantity: The quantity of the price_id.
        customer_id: Optional. The ID of an existing Stripe Customer.
                     If not provided, Stripe will create a new customer.
        metadata: Optional. A dictionary of key-value pairs to store with the session.
                  Useful for linking the session to your internal user IDs, order IDs, etc.
        request: Optional. The FastAPI request object, useful for constructing URLs.

    Returns:
        A Stripe Checkout Session object.

    Raises:
        HTTPException: If there's an error creating the session.
    """
    try:
        checkout_session_params = {
            "line_items": [
                {
                    "price": price_id,
                    "quantity": quantity,
                }
            ],
            "mode": "subscription",  # Or "payment" for one-time charges
            # Replace with your actual success and cancel URLs
            # These URLs are where Stripe redirects the user after payment.
            "success_url": f"{settings.FRONTEND_URL}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{settings.FRONTEND_URL}/payment/cancelled",
            "metadata": metadata if metadata else {},
        }

        if customer_id:
            checkout_session_params["customer"] = customer_id
        else:
            # Allow Stripe to create a customer or prompt for email
            checkout_session_params["customer_creation"] = "always" # Or "if_required"

        # Example: If you want to prefill the email for a new customer
        # if not customer_id and user_email:
        # checkout_session_params["customer_email"] = user_email

        # Example: For subscriptions, you might want to enable trial periods or payment method setup
        # checkout_session_params["subscription_data"] = {
        # "trial_period_days": 30, # Example trial
        # }

        session = stripe.checkout.Session.create(**checkout_session_params)
        return session
    except stripe.error.StripeError as e:
        # Log the error e.user_message or str(e)
        print(f"Stripe API error during checkout session creation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not create Stripe checkout session: {e.user_message or str(e)}",
        )
    except Exception as e:
        # Log the error
        print(f"Unexpected error during checkout session creation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while initiating payment.",
        )


async def create_customer_portal_session(
    customer_id: str,
    request: Optional[Request] = None # Pass request if you need to construct return_url dynamically
) -> stripe.billing_portal.Session:
    """
    Creates a Stripe Customer Portal session.
    This allows customers to manage their subscriptions, payment methods, etc.

    Args:
        customer_id: The ID of the Stripe Customer.
        request: Optional. The FastAPI request object, useful for constructing return_url.

    Returns:
        A Stripe Billing Portal Session object.

    Raises:
        HTTPException: If there's an error creating the session.
    """
    try:
        # Configure the return URL (where users are sent after leaving the portal)
        # This should be a page on your website.
        return_url = f"{settings.FRONTEND_URL}/account/billing" # Example

        portal_session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return portal_session
    except stripe.error.StripeError as e:
        print(f"Stripe API error during portal session creation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not create Stripe customer portal session: {e.user_message or str(e)}",
        )
    except Exception as e:
        # Log the error
        print(f"Unexpected error during customer portal session creation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while accessing customer portal.",
        )

async def get_stripe_customer_by_email(email: str) -> Optional[stripe.Customer]:
    """
    Retrieves a Stripe customer by their email address.

    Args:
        email: The email address of the customer to search for.

    Returns:
        A Stripe Customer object if found, otherwise None.
    """
    if not email:
        return None
    try:
        # Search for customers with the given email. limit=1 returns the most recent.
        customers = await asyncio.to_thread(
            stripe.Customer.list, email=email, limit=1
        )
        if customers.data:
            return customers.data[0]
        return None
    except stripe.error.StripeError as e:
        # Log the error, but for this function, we can return None as "not found".
        print(f"Stripe API error while getting customer by email '{email}': {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while getting customer by email '{email}': {e}")
        return None

async def create_stripe_customer(
    email: str,
    name: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[stripe.Customer]:
    """
    Creates a new customer in Stripe.

    Args:
        email: The customer's email address.
        name: The customer's full name.
        metadata: A dictionary of key-value data to attach to the customer object.
                  Useful for storing your internal user ID.

    Returns:
        The created Stripe Customer object, or None if creation fails.
    """
    if not email:
        return None
    try:
        customer_params = {
            "email": email,
            "name": name if name else "",
            "metadata": metadata if metadata else {},
        }
        customer = await asyncio.to_thread(stripe.Customer.create, **customer_params)
        return customer
    except stripe.error.StripeError as e:
        print(f"Stripe API error during customer creation for email '{email}': {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during customer creation for email '{email}': {e}")
        return None

async def get_subscription_status_from_stripe_id(subscription_id: str) -> Optional[str]:
    """(Placeholder) Retrieves the status of a Stripe subscription by its ID."""
    print(f"[TODO] Implement get_subscription_status_from_stripe_id for {subscription_id}")
    # Example: try:
    # subscription = stripe.Subscription.retrieve(subscription_id)
    # return subscription.status
    # except stripe.error.StripeError as e:
    # print(f"Stripe error while retrieving subscription: {e}")
    # return None
    return None

# --- Example Usage (Illustrative - would be called from your API endpoints) ---
# async def example_usage_checkout(request: Request):
#     try:
#         # Assume you have a price_id for your product/service
#         test_price_id = "price_xxxxxxxxxxxxxx" # Replace with an actual Price ID from your Stripe dashboard
#         # Assume you have a user_id or some internal identifier
#         internal_user_id = "user_123"
#
#         session = await create_stripe_checkout_session(
#             price_id=test_price_id,
#             metadata={"internal_user_id": internal_user_id, "product_name": "Premium Plan"},
#             request=request
#         )
#         return {"checkout_url": session.url}
#     except HTTPException as e:
#         return {"error": e.detail, "status_code": e.status_code}
#
# async def example_usage_portal(request: Request):
#     try:
#         # Assume you have a Stripe customer_id associated with your logged-in user
#         test_customer_id = "cus_xxxxxxxxxxxxxx" # Replace with an actual Customer ID
#
#         portal_session = await create_customer_portal_session(
#             customer_id=test_customer_id,
#             request=request
#         )
#         return {"portal_url": portal_session.url}
#     except HTTPException as e:
#         return {"error": e.detail, "status_code": e.status_code}

