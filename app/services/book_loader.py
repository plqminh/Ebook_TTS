import fitz
from ebooklib import epub
import ebooklib
from bs4 import BeautifulSoup
import docx
from pathlib import Path
from typing import List, Dict, Union, Any

class BookLoader:
    def __init__(self, file_path: str):
        self.path = Path(file_path)
        if not self.path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        self.ext = self.path.suffix.lower()
        self.doc = None
        self.epub_book = None
        self.docx_doc = None
        
        # Init resources
        if self.ext == '.pdf':
            self.doc = fitz.open(self.path)
        elif self.ext == '.epub':
            self.epub_book = epub.read_epub(str(self.path))
            self.epub_items = [] # Cache items for ID lookup
        elif self.ext == '.docx':
            self.docx_doc = docx.Document(self.path)
            
    def get_toc(self) -> List[Dict[str, Any]]:
        """
        Returns light metadata: [{'title': '...', 'id': internal_id}]
        """
        toc = []
        
        if self.ext == '.pdf':
            # PDF Pages as Chapters
            # Initialize all pages as generic
            for i in range(len(self.doc)):
                toc.append({"title": f"Page {i+1}", "id": i})
            
            # Apply TOC titles if available
            try:
                pdf_toc = self.doc.get_toc()
                for entry in pdf_toc:
                    lvl, title, page_num = entry
                    # page_num is 1-indexed
                    idx = page_num - 1
                    if 0 <= idx < len(toc):
                        toc[idx]["title"] = title
            except:
                pass
                
        elif self.ext == '.epub':
            # 1. Build Map of Href -> Title from TOC
            # TOC structure: [Link, (Section, [Link, Link]), Link]
            href_title_map = {}
            
            def parse_toc_node(node):
                if isinstance(node, tuple) or isinstance(node, list):
                    for sub in node: parse_toc_node(sub)
                elif isinstance(node, epub.Link):
                    href_title_map[node.href] = node.title
                elif isinstance(node, epub.Section):
                    if node.href: href_title_map[node.href] = node.title

            for item in self.epub_book.toc:
                parse_toc_node(item)
            
            # 2. Iterate Spine for Reading Order
            self.epub_items = []
            count = 1
            for item_id, linear in self.epub_book.spine:
                item = self.epub_book.get_item_with_id(item_id)
                if not item: continue
                
                self.epub_items.append(item)
                
                # Try to find title
                title = href_title_map.get(item.get_name(), None)
                
                # Fallback
                if not title:
                    title = f"Section {count}"
                
                toc.append({"title": title, "id": len(self.epub_items)-1})
                count += 1
                    
        elif self.ext == '.docx':
             toc.append({"title": "Document Content", "id": 0})
             
        elif self.ext == '.txt':
             toc.append({"title": "Text File", "id": 0})
             
        return toc

    def get_chapter_content(self, chapter_id: int) -> str:
        """
        Parses and returns text for the specific chapter ID.
        """
        if self.ext == '.pdf':
            if 0 <= chapter_id < len(self.doc):
                return self.doc[chapter_id].get_text()
            return ""
            
        elif self.ext == '.epub':
            if 0 <= chapter_id < len(self.epub_items):
                item = self.epub_items[chapter_id]
                soup = BeautifulSoup(item.get_content(), 'html.parser')
                
                # Attempt to extract a better title from the content while we are here?
                # Too late for TOC, but useful for display.
                return soup.get_text().strip()
            return ""
            
        elif self.ext == '.docx':
            return "\n".join([para.text for para in self.docx_doc.paragraphs])
            
        elif self.ext == '.txt':
            with open(self.path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()

        return ""

    def close(self):
        if self.doc:
            self.doc.close()
