# app/tests/core/test_security.py

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import time
from datetime import datetime, timedelta, timezone
from jose import jwt
from jose.utils import base64url_encode
import json
import httpx # Add httpx import for mocking its client

from app.core.security import (
    get_jwks,
    validate_token,
    clear_jwks_cache,
    get_jwks_cache_info,
    JWKSFetchError,
    TokenValidationError,
    RateLimitError,
    SecurityError
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
    with patch('app.core.security.httpx.AsyncClient') as mock_async_client_constructor:
        mock_client_instance_in_with_block = MagicMock()
        mock_get_method = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = MOCK_JWKS
        mock_response.raise_for_status.return_value = None
        mock_get_method.return_value = mock_response
        mock_client_instance_in_with_block.get = mock_get_method

        mock_constructor_return = MagicMock()
        mock_constructor_return.__aenter__.return_value = mock_client_instance_in_with_block
        mock_constructor_return.__aexit__.return_value = MagicMock()
        mock_async_client_constructor.return_value = mock_constructor_return

        # First call should fetch from network
        result = await get_jwks()
        assert result == MOCK_JWKS
        mock_get_method.assert_called_once()
        
        # Second call should use cache
        result = await get_jwks()
        assert result == MOCK_JWKS
        mock_get_method.assert_called_once()

@pytest.mark.asyncio
async def test_get_jwks_failure():
    """Test JWKS fetching failure handling."""
    clear_jwks_cache()
    with patch('app.core.security.httpx.AsyncClient') as mock_async_client_constructor:
        mock_client_instance_in_with_block = MagicMock()
        mock_get_method = AsyncMock()
        mock_get_method.side_effect = httpx.RequestError("Network error", request=None) # type: ignore
        mock_client_instance_in_with_block.get = mock_get_method

        mock_constructor_return = MagicMock()
        mock_constructor_return.__aenter__.return_value = mock_client_instance_in_with_block
        mock_constructor_return.__aexit__.return_value = MagicMock()
        mock_async_client_constructor.return_value = mock_constructor_return
        
        with pytest.raises(JWKSFetchError):
            await get_jwks()

@pytest.mark.asyncio
async def test_get_jwks_rate_limiting():
    """Test JWKS fetching rate limiting (currently expecting JWKSFetchError on retry without specific rate limit logic)."""
    clear_jwks_cache()
    with patch('app.core.security.httpx.AsyncClient') as mock_async_client_constructor:
        mock_client_instance_in_with_block = MagicMock()
        mock_get_method = AsyncMock()
        mock_get_method.side_effect = httpx.RequestError("Network error", request=None) # type: ignore
        mock_client_instance_in_with_block.get = mock_get_method

        mock_constructor_return = MagicMock()
        mock_constructor_return.__aenter__.return_value = mock_client_instance_in_with_block
        mock_constructor_return.__aexit__.return_value = MagicMock()
        mock_async_client_constructor.return_value = mock_constructor_return
        
        # First failure
        with pytest.raises(JWKSFetchError):
            await get_jwks()
        
        # Reset the side effect for the next call if needed, or use a list of side_effects
        mock_get_method.side_effect = httpx.RequestError("Network error on retry", request=None) # type: ignore
        with pytest.raises(JWKSFetchError): 
            await get_jwks()

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
    with patch('app.core.security.get_jwks') as mock_get_jwks:
        # Make the mock_get_jwks an async mock that returns MOCK_JWKS
        async def async_mock_get_jwks():
            return MOCK_JWKS
        mock_get_jwks.side_effect = async_mock_get_jwks # Use side_effect for async function mock

        with patch('jose.jwt.decode') as mock_decode:
            with patch('app.core.security.KINDE_DOMAIN', "test_issuer"), \
                 patch('app.core.security.KINDE_AUDIENCE', "test_audience"):
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
    with patch('app.core.security.get_jwks') as mock_get_jwks:
        async def async_mock_get_jwks(): return MOCK_JWKS
        mock_get_jwks.side_effect = async_mock_get_jwks
        
        with patch('app.core.security.KINDE_DOMAIN', "test_issuer"), \
             patch('app.core.security.KINDE_AUDIENCE', "test_audience"):
            with patch('jose.jwt.decode', side_effect=jwt.ExpiredSignatureError("Token has expired")) as mock_decode:
                with pytest.raises(TokenValidationError, match="Expired signature"):
                    await validate_token(MOCK_TOKEN) # Await the call

@pytest.mark.asyncio
async def test_validate_token_invalid_kid():
    """Test token validation with invalid key ID."""
    clear_jwks_cache()
    with patch('app.core.security.get_jwks') as mock_get_jwks:
        async def async_mock_get_jwks(): return {"keys": []} # No matching key
        mock_get_jwks.side_effect = async_mock_get_jwks
        
        with patch('app.core.security.KINDE_DOMAIN', "test_issuer"), \
             patch('app.core.security.KINDE_AUDIENCE', "test_audience"):
            with pytest.raises(TokenValidationError, match="Public key with kid 'test_key_1' not found"):
                await validate_token(MOCK_TOKEN) # Await the call

# --- Cache Management Tests ---
@pytest.mark.asyncio
async def test_clear_jwks_cache():
    """Test JWKS cache clearing."""
    clear_jwks_cache() 
    with patch('app.core.security.httpx.AsyncClient') as mock_async_client_constructor:
        mock_client_instance_in_with_block = MagicMock()
        mock_get_method = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = MOCK_JWKS
        mock_response.raise_for_status.return_value = None
        mock_get_method.return_value = mock_response
        mock_client_instance_in_with_block.get = mock_get_method
        
        mock_constructor_return = MagicMock()
        mock_constructor_return.__aenter__.return_value = mock_client_instance_in_with_block
        mock_constructor_return.__aexit__.return_value = MagicMock()
        mock_async_client_constructor.return_value = mock_constructor_return
        
        # First call populates cache
        await get_jwks()
        assert mock_get_method.call_count == 1, "httpx.AsyncClient.get should be called once to populate cache"
        
        # Clear cache
        clear_jwks_cache()
        
        # Next call should fetch again
        await get_jwks()
        assert mock_get_method.call_count == 2, "httpx.AsyncClient.get should be called again after cache clear"

@pytest.mark.asyncio
async def test_get_jwks_cache_info():
    """Test JWKS cache info retrieval."""
    clear_jwks_cache()
    with patch('app.core.security.httpx.AsyncClient') as mock_async_client_constructor:
        mock_client_instance_in_with_block = MagicMock()
        mock_get_method = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = MOCK_JWKS
        mock_response.raise_for_status.return_value = None
        mock_get_method.return_value = mock_response
        mock_client_instance_in_with_block.get = mock_get_method

        mock_constructor_return = MagicMock()
        mock_constructor_return.__aenter__.return_value = mock_client_instance_in_with_block
        mock_constructor_return.__aexit__.return_value = MagicMock()
        mock_async_client_constructor.return_value = mock_constructor_return
        
        # Populate cache
        await get_jwks()
        await get_jwks()
        
        # Get cache info (this function itself is not async)
        cache_info = get_jwks_cache_info()
        assert isinstance(cache_info, dict)
        assert "hits" in cache_info
        assert "misses" in cache_info
        assert "maxsize" in cache_info
        assert "currsize" in cache_info

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