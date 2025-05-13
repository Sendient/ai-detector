# app/services/text_extraction.py

import fitz  # PyMuPDF library (imported as fitz)
import docx # python-docx library
from io import BytesIO # To handle bytes as a file-like object for python-docx
import logging
from typing import Optional # For type hinting return value

# Assuming your enums are here, adjust the import path if needed
from app.models.enums import FileType

# Setup logger for this module
logger = logging.getLogger(__name__)

def extract_text_from_bytes(file_bytes: bytes, file_type: FileType) -> Optional[str]:
    """
    Extracts raw text content from file bytes based on the file type.

    Args:
        file_bytes: The content of the file as bytes.
        file_type: The enum member representing the file type (e.g., FileType.PDF).

    Returns:
        The extracted text as a single string, or None if extraction fails
        or the file type is not supported for text extraction.
    """
    extracted_text = ""
    logger.debug(f"Attempting text extraction for file type: {file_type.value if file_type else 'None'}")

    try:
        if file_type == FileType.PDF:
            # Use fitz (PyMuPDF) to open PDF from bytes
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                for page in doc:
                    extracted_text += page.get_text() + "\n" # Add newline between pages
            logger.info(f"Successfully extracted text from PDF ({len(extracted_text)} chars).")
            return extracted_text.strip() # Remove leading/trailing whitespace

        elif file_type == FileType.DOCX:
            # Use python-docx, requires BytesIO to treat bytes as a file
            document = docx.Document(BytesIO(file_bytes))
            for para in document.paragraphs:
                extracted_text += para.text + "\n" # Add newline between paragraphs
            logger.info(f"Successfully extracted text from DOCX ({len(extracted_text)} chars).")
            return extracted_text.strip() # Remove leading/trailing whitespace

        elif file_type in [FileType.TXT, FileType.TEXT]:
            # Decode TXT files, trying utf-8 first, then latin-1 as fallback
            try:
                extracted_text = file_bytes.decode('utf-8')
            except UnicodeDecodeError:
                logger.warning("UTF-8 decoding failed for TXT, trying latin-1.")
                # Ignore errors on fallback for potentially mixed content
                extracted_text = file_bytes.decode('latin-1', errors='ignore')
            logger.info(f"Successfully extracted text from TXT ({len(extracted_text)} chars).")
            return extracted_text.strip() # Remove leading/trailing whitespace

        else:
            # Handle unsupported types for text extraction (e.g., images)
            logger.warning(f"Text extraction not supported for file type: {file_type.value if file_type else 'None'}")
            return None # Explicitly return None for unsupported types

    except Exception as e:
        # Log any unexpected errors during extraction
        logger.error(f"Error during text extraction for file type {file_type.value if file_type else 'None'}: {e}", exc_info=True)
        return None # Indicate failure