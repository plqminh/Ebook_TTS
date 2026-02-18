import pytesseract
from PIL import Image
import io
import os
from typing import Optional

class OCRService:
    """
    Service to handle Optical Character Recognition (OCR) using Tesseract.
    Requires Tesseract-OCR to be installed on the system.
    """
    
    # Common default paths for Windows
    TESSERACT_CMD = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

    @staticmethod
    def _configure_tesseract():
        if os.path.exists(OCRService.TESSERACT_CMD):
            pytesseract.pytesseract.tesseract_cmd = OCRService.TESSERACT_CMD

    @classmethod
    def extract_text_from_image(cls, image_data: bytes, lang: str = 'vie') -> str:
        """
        Extracts text from an image byte stream.
        Defaults to Vietnamese ('vie').
        """
        cls._configure_tesseract()
        try:
            image = Image.open(io.BytesIO(image_data))
            text = pytesseract.image_to_string(image, lang=lang)
            return text
        except Exception as e:
            return f"Error performing OCR: {str(e)}\n(Make sure Tesseract is installed and in your PATH)"
