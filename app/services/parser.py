import fitz  # PyMuPDF
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import docx
from pathlib import Path
from typing import List, Dict, Optional

class FileParser:
    """
    Handles parsing of various file formats into structured chapters.
    """
    
    @staticmethod
    def extract_chapters(file_path: str) -> List[Dict[str, str]]:
        """
        Returns a list of chapters: [{'title': 'Chapter 1', 'content': '...'}, ...]
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
            
        ext = path.suffix.lower()
        
        if ext == '.pdf':
            return FileParser._parse_pdf_chapters(path)
        elif ext == '.epub':
            return FileParser._parse_epub_chapters(path)
        elif ext == '.docx':
            return FileParser._parse_docx_chapters(path)
        elif ext == '.txt':
            return FileParser._parse_txt_chapters(path)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

    @staticmethod
    def extract_text(file_path: str) -> str:
        # Legacy support: Flatten chapters
        chapters = FileParser.extract_chapters(file_path)
        return "\n\n".join([c['content'] for c in chapters])

    @staticmethod
    def _parse_pdf_chapters(path: Path) -> List[Dict]:
        chapters = []
        with fitz.open(path) as doc:
            for i, page in enumerate(doc):
                text = page.get_text()
                if text.strip():
                    chapters.append({
                        "title": f"Page {i+1}",
                        "content": text
                    })
        return chapters

    @staticmethod
    def _parse_epub_chapters(path: Path) -> List[Dict]:
        book = epub.read_epub(str(path))
        chapters = []
        # Naive approach: Iterate documents. EbookLib TOC is complex to parse flatly.
        # Ideally we traverse book.toc, but iterating items is robust for gathering content.
        count = 1
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                soup = BeautifulSoup(item.get_content(), 'html.parser')
                text = soup.get_text().strip()
                if text:
                    # Try to find a header
                    title = f"Section {count}"
                    h1 = soup.find('h1')
                    if h1: title = h1.get_text().strip()
                    elif soup.find('h2'): title = soup.find('h2').get_text().strip()
                    
                    chapters.append({
                        "title": title,
                        "content": text
                    })
                    count += 1
        return chapters

    @staticmethod
    def _parse_docx_chapters(path: Path) -> List[Dict]:
        doc = docx.Document(path)
        # return entire doc as one chapter for now
        text = "\n".join([para.text for para in doc.paragraphs])
        return [{"title": "Document Content", "content": text}]

    @staticmethod
    def _parse_txt_chapters(path: Path) -> List[Dict]:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return [{"title": "Text File", "content": f.read()}]
