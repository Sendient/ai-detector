# app/tests/core/test_security.py

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import time
from datetime import datetime, timedelta, timezone
from jose import jwt
from jose.utils import base64url_encode
import json
import httpx # Add httpx import for mocking its client

from backend.app.core.security import (
    get_jwks,
    validate_token,
    clear_jwks_cache,
    get_jwks_cache_info,
    JWKSFetchError,
    TokenValidationError,
    RateLimitError,
    SecurityError,
    JWKS_URL # Import JWKS_URL
)

# --- Test Data ---
MOCK_JWKS = {
    "keys": [
        {
            "kid": "test_key_1",
            "kty": "RSA",
            "n": "test_n",
            "e": "AQAB",
            "use": "sig",
            "alg": "RS256"
        }
    ]
}

# Structurally valid mock token with a kid that matches MOCK_JWKS
_mock_header = {"alg": "RS256", "typ": "JWT", "kid": "test_key_1"}
_mock_header_b64 = base64url_encode(json.dumps(_mock_header).encode('utf-8')).decode('utf-8')
_mock_payload_empty_b64 = base64url_encode(b'{}').decode('utf-8') # Empty payload for simplicity as jwt.decode is mocked
_mock_signature_b64 = base64url_encode(b"fakesignature").decode('utf-8') # Valid base64url signature
MOCK_TOKEN = f"{_mock_header_b64}.{_mock_payload_empty_b64}.{_mock_signature_b64}"

MOCK_PAYLOAD = {
    "sub": "test_user",
    "aud": "test_audience",
    "iss": "test_issuer",
    "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
}

# --- JWKS Tests ---
@pytest.mark.asyncio
async def test_get_jwks_success():
    """Test successful JWKS fetching and caching."""
    clear_jwks_cache()
    # Mock httpx.AsyncClient context manager and its get method
    with patch('backend.app.core.security.httpx.AsyncClient') as mock_async_client_constructor:
        # Mock the response object
        mock_response = MagicMock()
        mock_response.json.return_value = MOCK_JWKS
        mock_response.raise_for_status.return_value = None # Simulate successful response

        # Mock the get method on the client instance to return an awaitable response
        # Use AsyncMock for the client instance itself if needed, but mocking the get method directly is often simpler
        mock_async_client = AsyncMock() # Mock the client instance returned by __aenter__
        mock_async_client.get.return_value = mock_response # .get should return the mock response
        # NOTE: httpx client methods like .get() are typically async, but the mock framework
        # often handles this if the return_value is set. If tests still fail with TypeError,
        # you might need: mock_async_client.get = AsyncMock(return_value=mock_response)
        # However, the structure below using the context manager mock is generally preferred.

        # Mock the async context manager behavior (__aenter__)
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_async_client # Entering the context returns the mock client
        mock_async_client_constructor.return_value = mock_context_manager # Calling AsyncClient() returns the context manager

        # First call should fetch from network
        result = await get_jwks()
        assert result == MOCK_JWKS
        # Ensure the mock was called
        mock_async_client_constructor.assert_called_once()
        mock_async_client.get.assert_called_once_with(JWKS_URL)

        # Second call should return from cache (mock shouldn't be called again)
        mock_async_client_constructor.reset_mock()
        mock_async_client.get.reset_mock()
        result_cached = await get_jwks()
        assert result_cached == MOCK_JWKS
        mock_async_client_constructor.assert_not_called() # Should not create a new client
        mock_async_client.get.assert_not_called() # Should not make a new GET request

@pytest.mark.asyncio
async def test_get_jwks_failure():
    """Test JWKS fetching failure handling."""
    clear_jwks_cache()
    with patch('backend.app.core.security.httpx.AsyncClient') as mock_async_client_constructor:
        mock_async_client = MagicMock()
        # Make the get call raise an httpx.RequestError (or similar)
        mock_async_client.get.side_effect = httpx.RequestError("Network error", request=None) # type: ignore

        mock_instance = MagicMock()
        mock_instance.__aenter__.return_value = mock_async_client
        mock_async_client_constructor.return_value = mock_instance
        
        with pytest.raises(JWKSFetchError):
            await get_jwks() # Await the call

@pytest.mark.asyncio
async def test_get_jwks_rate_limiting():
    """Test JWKS fetching rate limiting (currently expecting JWKSFetchError on retry without specific rate limit logic)."""
    clear_jwks_cache()
    with patch('backend.app.core.security.httpx.AsyncClient') as mock_async_client_constructor:
        mock_async_client = MagicMock()
        mock_async_client.get.side_effect = httpx.RequestError("Network error", request=None) # type: ignore

        mock_instance = MagicMock()
        mock_instance.__aenter__.return_value = mock_async_client
        mock_async_client_constructor.return_value = mock_instance
        
        # First failure
        with pytest.raises(JWKSFetchError):
            await get_jwks() # Await the call
        
        # Reset the side effect for the next call if needed, or use a list of side_effects
        mock_async_client.get.side_effect = httpx.RequestError("Network error on retry", request=None) # type: ignore
        with pytest.raises(JWKSFetchError): 
            await get_jwks() # Await the call

# --- Token Validation Tests ---
@pytest.mark.asyncio
async def test_validate_token_success():
    """Test successful token validation."""
    clear_jwks_cache()
    # get_jwks is now async and will be called by validate_token
    # We need to ensure that if get_jwks is called, it returns MOCK_JWKS
    # So, we patch get_jwks itself here as it's a dependency of validate_token.
    # Alternatively, we could patch httpx.AsyncClient like above if we want to test get_jwks through validate_token.
    # For simplicity and focused testing of validate_token logic, patching get_jwks directly is often easier.
    with patch('backend.app.core.security.get_jwks') as mock_get_jwks:
        # Make the mock_get_jwks an async mock that returns MOCK_JWKS
        async def async_mock_get_jwks():
            return MOCK_JWKS
        mock_get_jwks.side_effect = async_mock_get_jwks # Use side_effect for async function mock

        with patch('jose.jwt.decode') as mock_decode:
            with patch('backend.app.core.security.KINDE_DOMAIN', "test_issuer"), \
                 patch('backend.app.core.security.KINDE_AUDIENCE', "test_audience"):
                mock_decode.return_value = MOCK_PAYLOAD
                
                result = await validate_token(MOCK_TOKEN) # Await the call
                assert result == MOCK_PAYLOAD
                mock_get_jwks.assert_called_once() # Ensure get_jwks was called
                mock_decode.assert_called_once_with(
                    MOCK_TOKEN,
                    MOCK_JWKS['keys'][0],
                    algorithms=["RS256"],
                    audience="test_audience",
                    issuer="test_issuer"
                )

@pytest.mark.asyncio
async def test_validate_token_expired():
    """Test expired token validation."""
    clear_jwks_cache()
    with patch('backend.app.core.security.get_jwks') as mock_get_jwks:
        async def async_mock_get_jwks(): return MOCK_JWKS
        mock_get_jwks.side_effect = async_mock_get_jwks
        
        with patch('backend.app.core.security.KINDE_DOMAIN', "test_issuer"), \
             patch('backend.app.core.security.KINDE_AUDIENCE', "test_audience"):
            with patch('jose.jwt.decode', side_effect=jwt.ExpiredSignatureError("Token has expired")) as mock_decode:
                with pytest.raises(TokenValidationError, match="Expired signature"):
                    await validate_token(MOCK_TOKEN) # Await the call

@pytest.mark.asyncio
async def test_validate_token_invalid_kid():
    """Test token validation with invalid key ID."""
    clear_jwks_cache()
    with patch('backend.app.core.security.get_jwks') as mock_get_jwks:
        async def async_mock_get_jwks(): return {"keys": []} # No matching key
        mock_get_jwks.side_effect = async_mock_get_jwks
        
        with patch('backend.app.core.security.KINDE_DOMAIN', "test_issuer"), \
             patch('backend.app.core.security.KINDE_AUDIENCE', "test_audience"):
            with pytest.raises(TokenValidationError, match="Public key with kid 'test_key_1' not found"):
                await validate_token(MOCK_TOKEN) # Await the call

# --- Cache Management Tests ---
@pytest.mark.asyncio
async def test_clear_jwks_cache():
    """Test JWKS cache clearing."""
    clear_jwks_cache()
    with patch('backend.app.core.security.httpx.AsyncClient') as mock_async_client_constructor:
        mock_response = MagicMock()
        mock_response.json.return_value = MOCK_JWKS
        mock_response.raise_for_status.return_value = None

        mock_async_client = AsyncMock()
        mock_async_client.get.return_value = mock_response

        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_async_client
        mock_async_client_constructor.return_value = mock_context_manager

        # First call populates cache
        await get_jwks()
        cache_info_before = get_jwks_cache_info()
        assert cache_info_before["cached"]

        # Clear the cache
        clear_jwks_cache()
        cache_info_after = get_jwks_cache_info()
        assert not cache_info_after["cached"]
        assert cache_info_after["timestamp"] is None

        # Third call should fetch again
        await get_jwks()
        # Check that the mock was called again after cache clear
        assert mock_async_client.get.call_count == 2 # Called once before clear, once after

@pytest.mark.asyncio
async def test_get_jwks_cache_info():
    """Test JWKS cache info retrieval."""
    clear_jwks_cache()
    with patch('backend.app.core.security.httpx.AsyncClient') as mock_async_client_constructor:
        mock_response = MagicMock()
        mock_response.json.return_value = MOCK_JWKS
        mock_response.raise_for_status.return_value = None

        mock_async_client = AsyncMock()
        mock_async_client.get.return_value = mock_response

        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_async_client
        mock_async_client_constructor.return_value = mock_context_manager

        # Check cache info before population
        info_before = get_jwks_cache_info()
        assert not info_before["cached"]
        assert info_before["timestamp"] is None

        # Populate cache
        await get_jwks()
        timestamp_after_fetch = datetime.now(timezone.utc)

        # Check cache info after population
        info_after = get_jwks_cache_info()
        assert info_after["cached"]
        assert info_after["timestamp"] is not None
        # Check if timestamp is close to now (within a small delta)
        cached_timestamp = datetime.fromisoformat(info_after["timestamp"])
        assert abs(cached_timestamp - timestamp_after_fetch) < timedelta(seconds=1)

# --- Error Handling Tests ---
@pytest.mark.asyncio
async def test_security_error_hierarchy():
    """Test security error class hierarchy."""
    assert issubclass(JWKSFetchError, SecurityError)
    assert issubclass(TokenValidationError, SecurityError)
    assert issubclass(RateLimitError, SecurityError)

@pytest.mark.asyncio
async def test_error_messages():
    """Test error message formatting."""
    with pytest.raises(JWKSFetchError, match="Test error"):
        raise JWKSFetchError("Test error") 