# app/core/security.py
"""
Security module for handling Kinde JWT authentication.

Provides functionality for:
- JWKS (JSON Web Key Set) fetching and caching using lru_cache.
- JWT token validation (signature, expiry, claims: iss, aud).
- FastAPI dependency for protecting endpoints.
- Custom exceptions for specific security errors.
- Cache management utilities.

Security Considerations:
- Uses lru_cache for JWKS to prevent excessive network calls.
- Uses proper error handling and logging.
- Validates required token claims (iss, aud, exp, signature).

Example Usage in Endpoints:
    ```python
    from fastapi import APIRouter, Depends, HTTPException
    from typing import Dict, Any
    from ...core.security import get_current_user_payload # Adjust import path

    router = APIRouter()

    @router.get("/protected-resource")
    async def get_protected_resource(
        payload: Dict[str, Any] = Depends(get_current_user_payload)
    ):
        # If code reaches here, token is valid. Payload contains claims.
        user_id = payload.get("sub")
        # ... process request using user_id or other claims ...
        return {"message": f"Hello user {user_id}", "claims": payload}
    ```
"""

import logging
import httpx # Changed from requests
from typing import Dict, Any, Optional
from functools import lru_cache
from datetime import datetime, timedelta, timezone # Added timezone and timedelta

# --- JOSE & JWT Imports ---
from jose import jwt, exceptions as jose_exceptions
from jose.exceptions import JOSEError

# --- FastAPI Imports ---
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# --- Config Imports ---
# Import Kinde settings from config
# Adjust the relative path '.' based on where security.py is relative to 'core'
from .config import KINDE_DOMAIN, KINDE_AUDIENCE

# Setup logging
logger = logging.getLogger(__name__)
# Ensure logging is configured elsewhere (e.g., main.py or logging config)
# logging.basicConfig(level=logging.INFO) # Avoid configuring basicConfig here if done elsewhere

# --- Custom Exceptions ---
class SecurityError(Exception):
    """Base class for security-related exceptions."""
    pass

class JWKSFetchError(SecurityError):
    """Raised when there is an error fetching or parsing the JWKS."""
    pass

class TokenValidationError(SecurityError):
    """Raised when token validation fails (expiry, signature, claims, etc.)."""
    pass

class RateLimitError(SecurityError):
    """Raised when an operation is rate-limited."""
    pass

# --- JWKS Handling ---

# Construct the JWKS URL based on the Kinde domain from config
JWKS_URL: Optional[str] = None
if KINDE_DOMAIN:
    # Ensure domain doesn't have trailing slash for clean URL join
    domain = KINDE_DOMAIN.rstrip('/')
    JWKS_URL = f"{domain}/.well-known/jwks.json"
else:
    logger.error("KINDE_DOMAIN is not configured. Cannot determine JWKS URL.")

# --- Manual Cache for JWKS ---
_jwks_cache: Optional[Dict[str, Any]] = None
_jwks_cache_timestamp: Optional[datetime] = None
JWKS_CACHE_TTL = timedelta(hours=1) # Cache JWKS for 1 hour
# --- End Manual Cache --- 

# @lru_cache(maxsize=1) # REMOVED: lru_cache is not directly compatible with async def for this use case
async def get_jwks() -> Dict[str, Any]:
    """
    Fetches the JWKS keys from the Kinde instance's well-known endpoint.
    Uses a simple time-based in-memory cache. Raises JWKSFetchError on failure.
    Now uses httpx for asynchronous requests.
    """
    global _jwks_cache, _jwks_cache_timestamp

    # Check cache validity
    if _jwks_cache and _jwks_cache_timestamp and \
       (datetime.now(timezone.utc) - _jwks_cache_timestamp < JWKS_CACHE_TTL):
        logger.info(f"Returning JWKS from cache (timestamp: {_jwks_cache_timestamp}, TTL: {JWKS_CACHE_TTL}).")
        return _jwks_cache

    if not JWKS_URL:
        err_msg = "Cannot fetch JWKS: JWKS URL is not configured (KINDE_DOMAIN missing?)."
        logger.error(err_msg)
        raise JWKSFetchError(err_msg)

    logger.info(f"Attempting to fetch JWKS keys from {JWKS_URL}...")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client: # Network timeout
            response = await client.get(JWKS_URL)
            response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)

            jwks = response.json()
            if "keys" not in jwks or not isinstance(jwks["keys"], list):
                raise JWKSFetchError("Invalid JWKS format received: \'keys\' array not found.")

            logger.info(f"Successfully fetched {len(jwks['keys'])} JWKS keys. Updating cache.")
            _jwks_cache = jwks # Store result in cache
            _jwks_cache_timestamp = datetime.now(timezone.utc) # Update timestamp
            return jwks

    except httpx.TimeoutException as e:
        raise JWKSFetchError(f"Timeout while trying to fetch JWKS from {JWKS_URL}: {e}")
    except httpx.RequestError as e: # Catches various httpx request errors
        raise JWKSFetchError(f"Network error fetching JWKS from {JWKS_URL}: {e}")
    except ValueError as e: # Includes JSONDecodeError
        raise JWKSFetchError(f"Error parsing JWKS JSON response from {JWKS_URL}: {e}")
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"Unexpected error during JWKS fetch: {e}", exc_info=True)
        raise JWKSFetchError(f"Unexpected error during JWKS fetch: {e}")


# --- JWT Validation Function ---

async def validate_token(token: str) -> Dict[str, Any]: # Changed to async def
    """
    Decodes and validates a JWT token using Kinde's public keys.
    Now asynchronous as it calls get_jwks.

    Args:
        token: The encoded JWT string (access token).

    Returns:
        The decoded token payload (dictionary) if validation is successful.

    Raises:
        TokenValidationError: If Kinde config is missing or token validation fails
                              (e.g., signature, expiry, claims).
        JWKSFetchError: If fetching the required JWKS keys fails.
    """
    if not KINDE_DOMAIN or not KINDE_AUDIENCE:
        raise TokenValidationError("Kinde domain or audience not configured.")

    try:
        jwks = await get_jwks() # Await the async get_jwks()
    except JWKSFetchError as e:
         raise TokenValidationError(f"Token validation failed: Could not retrieve JWKS keys - {e}")

    # 2. Get the Key ID (kid) from the unverified token header
    try:
        unverified_header = jwt.get_unverified_header(token)
        if "kid" not in unverified_header:
             raise TokenValidationError("JWT header does not contain \'kid\' (Key ID).")
        rsa_key_kid = unverified_header["kid"]
    except jose_exceptions.JWTError as e:
        raise TokenValidationError(f"Error getting unverified header from token: {e}")

    # 3. Find the key in JWKS that matches the token\'s \'kid\'
    key_found = None
    for key in jwks["keys"]:
        if key.get("kid") == rsa_key_kid:
            key_found = key
            break

    if not key_found:
        clear_jwks_cache() 
        logger.warning(f"Public key with kid \'{rsa_key_kid}\' not found in JWKS. Cache cleared.")
        # Consider if get_jwks should be called again here after clearing cache
        # For now, raising error directly.
        raise TokenValidationError(f"Public key with kid \'{rsa_key_kid}\' not found in JWKS (cache cleared, retry might succeed).")

    # 4. Decode and validate the token
    try:
        payload = jwt.decode(
            token,
            key_found, 
            algorithms=["RS256"], 
            audience=KINDE_AUDIENCE, 
            issuer=KINDE_DOMAIN      
        )
        logger.info("Token successfully validated.")
        return payload

    except jose_exceptions.ExpiredSignatureError:
        raise TokenValidationError("Token validation failed: Expired signature.")
    except jose_exceptions.JWTClaimsError as e:
        raise TokenValidationError(f"Token validation failed: Invalid claims - {e}")
    except jose_exceptions.JWTError as e:
        raise TokenValidationError(f"Token validation failed: Invalid token - {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during token validation: {e}", exc_info=True)
        raise TokenValidationError(f"Unexpected error during token validation: {e}")


# --- FastAPI Dependency for Authentication ---

# Define the OAuth2 scheme - extracts Bearer token from Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)
# Set auto_error=False to handle missing token within our dependency for clearer error

async def get_current_user_payload( # Already async, which is good
    token: Optional[str] = Depends(oauth2_scheme) 
) -> Dict[str, Any]:
    """
    FastAPI dependency to validate Kinde token and return payload.
    Now calls asynchronous validate_token.

    Usage: Add `payload: Dict[str, Any] = Depends(get_current_user_payload)`
           to endpoint function signatures.

    Raises:
        HTTPException(401): If token is missing, invalid, expired, or fails validation.
        HTTPException(500): If an unexpected internal error occurs.

    Returns:
        Dict[str, Any]: The decoded and validated JWT payload upon success.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    internal_error_exception = HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An internal error occurred during authentication.",
    )

    if token is None:
         logger.warning("Authentication attempt failed: No token provided.")
         raise credentials_exception 

    try:
        payload = await validate_token(token) # Await the async validate_token()
        return payload
    except TokenValidationError as e:
        logger.warning(f"Authentication failed: {e}") 
        raise credentials_exception from e
    except JWKSFetchError as e: # This might be less likely now if validate_token wraps it
         logger.error(f"Authentication failed due to JWKS fetch error: {e}")
         raise internal_error_exception from e # Or map to a 401/403 if preferred
    except HTTPException as http_exc: # Add this block
        logger.warning(f"HTTPException during authentication dependency: {http_exc.status_code} - {http_exc.detail}")
        raise http_exc # Re-raise the original HTTPException
    except Exception as e:
        logger.error(f"Unexpected error during authentication dependency: {e}", exc_info=True)
        raise internal_error_exception from e


# --- Cache Management Functions ---

def clear_jwks_cache():
    """Clears the JWKS cache, forcing a fresh fetch on the next call to get_jwks."""
    # get_jwks.cache_clear() # REMOVED: No longer using lru_cache on get_jwks directly
    global _jwks_cache, _jwks_cache_timestamp
    _jwks_cache = None
    _jwks_cache_timestamp = None
    logger.info("Manually cleared JWKS cache.")

def get_jwks_cache_info() -> Dict[str, Any]:
    """Gets information about the current JWKS cache state (manual cache)."""
    # cache_info = get_jwks.cache_info() # REMOVED
    # return {
    #     "hits": cache_info.hits,
    #     "misses": cache_info.misses,
    #     "maxsize": cache_info.maxsize,
    #     "currsize": cache_info.currsize,
    # }
    global _jwks_cache, _jwks_cache_timestamp
    return {
        "cached": _jwks_cache is not None,
        "timestamp": _jwks_cache_timestamp.isoformat() if _jwks_cache_timestamp else None,
        "expires_in_seconds": (JWKS_CACHE_TTL - (datetime.now(timezone.utc) - _jwks_cache_timestamp)).total_seconds() 
                               if _jwks_cache and _jwks_cache_timestamp else None,
        "ttl_seconds": JWKS_CACHE_TTL.total_seconds()
    }
