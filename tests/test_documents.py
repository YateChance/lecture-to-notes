import json
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from lecture_agent.documents import ready


class DocumentReadinessTests(TestCase):
    def test_selected_text_and_page_image_are_required(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'lesson.yaml').write_text('documents:\n  sources:\n    - id: book\n      path: missing.pdf\n      pdf_page_ranges: [[1, 1]]\n      visual_pages: [1]\n')
            (root/'05_documents').mkdir()
            (root/'book.pdf').write_bytes(b'pdf')
            (root/'page.txt').write_text('text')
            page={'pdf_page':1,'printed_page':None,'text':'page.txt','image':'page.png'}
            (root/'05_documents/documents.json').write_text(json.dumps({'documents':[{'id':'book','archive_path':'book.pdf','sha256':hashlib.sha256(b'pdf').hexdigest(),'selected_pages':[page]}]}))
            self.assertFalse(ready(root))
            (root/'page.png').write_bytes(b'image')
            self.assertTrue(ready(root))
            (root/'book.pdf').write_bytes(b'changed')
            self.assertFalse(ready(root))
