# app/services/blob_storage.py

import logging
import uuid
import os
from typing import Optional

# --- Azure SDK Imports ---
# Use the async client for FastAPI compatibility
from azure.storage.blob.aio import BlobServiceClient, ContainerClient, BlobClient
# Import ResourceNotFoundError for specific exception handling during download
from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.storage.blob import ContentSettings # To set content type

# --- FastAPI Imports (for type hinting) ---
from fastapi import UploadFile

# --- Config Imports ---
# Adjust path based on your structure
from ..core.config import AZURE_BLOB_CONNECTION_STRING, AZURE_BLOB_CONTAINER_NAME

# --- Logging Setup ---
logger = logging.getLogger(__name__)
# Ensure logging is configured elsewhere (e.g., main.py or logging config)

# --- Blob Service Client (Cached) ---
# Using a simple global variable for simplicity here.
_blob_service_client: Optional[BlobServiceClient] = None

def get_blob_service_client() -> Optional[BlobServiceClient]:
    """Gets or creates the async BlobServiceClient instance."""
    global _blob_service_client
    if _blob_service_client is None:
        if not AZURE_BLOB_CONNECTION_STRING:
            logger.error("Azure Blob Storage connection string is not configured.")
            return None
        try:
            # Create client from connection string
            _blob_service_client = BlobServiceClient.from_connection_string(
                conn_str=AZURE_BLOB_CONNECTION_STRING
            )
            logger.info("BlobServiceClient initialized.")
        except ValueError as e:
            logger.error(f"Invalid Blob Storage connection string format: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to initialize BlobServiceClient: {e}", exc_info=True)
            return None
    return _blob_service_client

# --- File Upload Function ---

async def upload_file_to_blob(
    upload_file: UploadFile, # Use FastAPI's UploadFile type
) -> Optional[str]:
    """
    Uploads a file to Azure Blob Storage in the configured container.

    Args:
        upload_file: The UploadFile object received from the FastAPI request.

    Returns:
        The unique name of the blob created in the container if successful,
        otherwise None.
    """
    service_client = get_blob_service_client()
    if not service_client or not AZURE_BLOB_CONTAINER_NAME:
        logger.error("Blob storage service client or container name not available.")
        return None

    original_filename = upload_file.filename or "unknown_file"
    _, file_extension = os.path.splitext(original_filename)
    blob_name = f"{uuid.uuid4()}{file_extension}"
    content_type = upload_file.content_type

    logger.info(f"Attempting to upload '{original_filename}' as blob '{blob_name}' to container '{AZURE_BLOB_CONTAINER_NAME}'...")

    try:
        container_client: ContainerClient = service_client.get_container_client(AZURE_BLOB_CONTAINER_NAME)
        blob_client: BlobClient = container_client.get_blob_client(blob_name)
        file_stream = upload_file.file
        content_settings = ContentSettings(content_type=content_type) if content_type else None

        await blob_client.upload_blob(
            data=file_stream,
            overwrite=True,
            content_settings=content_settings
        )

        logger.info(f"Successfully uploaded '{original_filename}' to blob: {blob_name}")
        return blob_name

    except AzureError as e:
        logger.error(f"Azure error during blob upload for {blob_name}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during blob upload for {blob_name}: {e}", exc_info=True)
        return None


# --- NEW FUNCTION TO DOWNLOAD BLOB CONTENT ---
async def download_blob_as_bytes(blob_name: str) -> Optional[bytes]:
    """
    Downloads the content of a specific blob from Azure Blob Storage.

    Args:
        blob_name: The name of the blob (including any path/prefix) to download.

    Returns:
        The content of the blob as bytes, or None if the blob doesn't exist
        or an error occurs during download.
    """
    service_client = get_blob_service_client() # Use the helper
    if not service_client or not AZURE_BLOB_CONTAINER_NAME: # Check client and container name
        logger.error("Blob storage service client or container name not available for download.")
        return None

    logger.debug(f"Attempting to download blob '{blob_name}' from container '{AZURE_BLOB_CONTAINER_NAME}'")
    try:
        # Get blob client directly from the service client instance
        blob_client: BlobClient = service_client.get_blob_client(
            container=AZURE_BLOB_CONTAINER_NAME,
            blob=blob_name
        )

        # Check if blob exists before attempting download
        if not await blob_client.exists():
            logger.warning(f"Blob '{blob_name}' not found in container '{AZURE_BLOB_CONTAINER_NAME}'.")
            return None

        # Download blob content
        logger.debug(f"Blob '{blob_name}' exists, attempting download.")
        download_stream = await blob_client.download_blob()
        file_bytes = await download_stream.readall()
        logger.info(f"Successfully downloaded {len(file_bytes)} bytes from blob '{blob_name}'.")
        return file_bytes

    except ResourceNotFoundError: # Catch specific Azure "Not Found" error
        logger.warning(f"Blob '{blob_name}' not found during download attempt (ResourceNotFoundError).")
        return None
    except AzureError as ae: # Catch other Azure SDK errors
         logger.error(f"Azure error downloading blob '{blob_name}': {ae}", exc_info=False) # Less verbose for AzureError
         return None
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"Unexpected error downloading blob '{blob_name}': {e}", exc_info=True)
        return None
# --- END NEW FUNCTION ---


# --- Optional: Add functions for delete, list etc. later if needed ---
# async def delete_blob(blob_name: str) -> bool: ...
# async def get_blob_sas_url(blob_name: str) -> Optional[str]: ...

# --- NEW FUNCTION TO DELETE BLOB ---
async def delete_blob(blob_name_to_delete: str) -> bool:
    """
    Deletes a specific blob from Azure Blob Storage.

    Args:
        blob_name_to_delete: The name of the blob to delete.
                             It's assumed this is just the blob name (e.g., 'guid.ext')
                             and not a full path or URL.

    Returns:
        True if the blob was deleted successfully or was not found (idempotent).
        False if an error occurred during deletion.
    """
    service_client = get_blob_service_client() # Use the async helper
    if not service_client: # AZURE_BLOB_CONNECTION_STRING is checked in get_blob_service_client
        # Error already logged by get_blob_service_client if connection string is missing
        return False
    
    if not AZURE_BLOB_CONTAINER_NAME:
        logger.error("Azure Blob Storage container name (AZURE_BLOB_CONTAINER_NAME) is not configured.")
        return False

    # Clean the blob name just in case a full path/URL was passed, though the docstring assumes not.
    # This logic can be simplified if blob_name_to_delete is guaranteed to be just the name.
    if '/' in blob_name_to_delete:
        actual_blob_name = blob_name_to_delete.split("/")[-1]
        logger.warning(f"Full path ('{blob_name_to_delete}') provided to delete_blob, using only name: '{actual_blob_name}'.")
    else:
        actual_blob_name = blob_name_to_delete

    logger.info(f"Attempting to delete blob '{actual_blob_name}' from container '{AZURE_BLOB_CONTAINER_NAME}'")
    try:
        blob_client: BlobClient = service_client.get_blob_client(
            container=AZURE_BLOB_CONTAINER_NAME,
            blob=actual_blob_name
        )

        # Check if blob exists before attempting deletion for idempotency and clearer logging
        if await blob_client.exists():
            await blob_client.delete_blob(delete_snapshots="include") # Ensure snapshots are also deleted
            logger.info(f"Successfully deleted blob '{actual_blob_name}' from container '{AZURE_BLOB_CONTAINER_NAME}'.")
        else:
            logger.warning(f"Blob '{actual_blob_name}' not found in container '{AZURE_BLOB_CONTAINER_NAME}'. Deletion considered successful (idempotent).")
        return True

    except ResourceNotFoundError:
        # This might be redundant if blob_client.exists() is used, but good for safety
        logger.warning(f"Blob '{actual_blob_name}' not found during deletion attempt (ResourceNotFoundError). Considered successful.")
        return True
    except AzureError as ae:
        logger.error(f"Azure error deleting blob '{actual_blob_name}': {ae}", exc_info=False)
        return False
    except Exception as e:
        logger.error(f"Unexpected error deleting blob '{actual_blob_name}': {e}", exc_info=True)
        return False
# --- END NEW DELETE FUNCTION ---