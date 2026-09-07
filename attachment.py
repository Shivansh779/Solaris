"""File attachment system for Solaris - modular file ingestion and temporary context management."""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime

import pypdf
from PIL import Image


SUPPORTED_EXTENSIONS = {
    '.md': 'markdown',
    '.pdf': 'pdf',
    '.jpg': 'jpeg',
    '.jpeg': 'jpeg',
    '.png': 'png',
}


_attachment_context: Dict[str, Dict[str, Any]] = {}


def get_attachment_context() -> Dict[str, Dict[str, Any]]:
    """Get the current temporary attachment context."""
    return _attachment_context


def clear_attachment_context() -> None:
    """Clear all temporary attachment context (e.g., on session end)."""
    _attachment_context.clear()


def remove_attachment(index: int) -> Optional[Dict[str, Any]]:
    """Remove an attachment by its 0-based index in the insertion-order dict.
    Returns the removed attachment dict, or None if index is out of range."""
    if index < 0 or index >= len(_attachment_context):
        return None
    path = list(_attachment_context.keys())[index]
    removed = _attachment_context.pop(path)
    return removed


def get_file_type(file_path: str) -> Optional[str]:
    """Determine the supported file type from extension."""
    ext = Path(file_path).suffix.lower()
    return SUPPORTED_EXTENSIONS.get(ext)


def validate_file_path(file_path: str) -> Tuple[bool, str]:
    """Validate that the file path exists and is a supported type."""
    if not file_path:
        return False, "No file path provided."

    if not os.path.isabs(file_path):
        return False, "Path must be absolute. Please provide the full absolute path to the file."

    if not os.path.exists(file_path):
        return False, f"File not found: {file_path}"

    if not os.path.isfile(file_path):
        return False, f"Path is not a file: {file_path}"

    file_type = get_file_type(file_path)
    if not file_type:
        supported = ', '.join(sorted(SUPPORTED_EXTENSIONS.keys()))
        return False, f"Unsupported file type. Supported types: {supported}"

    return True, ""


def read_markdown(file_path: str) -> Tuple[bool, str, Dict[str, Any]]:
    """Read a Markdown file as text."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if not content.strip():
            return False, "Markdown file is empty.", {}

        metadata = {
            'type': 'markdown',
            'size_bytes': os.path.getsize(file_path),
            'char_count': len(content),
            'line_count': content.count('\n') + 1,
        }
        return True, content, metadata
    except UnicodeDecodeError:
        return False, "Markdown file contains invalid UTF-8 encoding.", {}
    except Exception as e:
        return False, f"Failed to read Markdown file: {e}", {}


def read_pdf(file_path: str) -> Tuple[bool, str, Dict[str, Any]]:
    """Extract text from a PDF file."""
    try:
        reader = pypdf.PdfReader(file_path)
        num_pages = len(reader.pages)

        if num_pages == 0:
            return False, "PDF file has no pages.", {}

        text_parts = []
        for i, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text()
                if page_text and page_text.strip():
                    text_parts.append(f"--- Page {i+1} ---\n{page_text.strip()}")
            except Exception:
                continue

        if not text_parts:
            return False, "PDF appears to be scanned/image-only (no extractable text). OCR is not supported in this version.", {}

        content = "\n\n".join(text_parts)
        metadata = {
            'type': 'pdf',
            'size_bytes': os.path.getsize(file_path),
            'page_count': num_pages,
            'char_count': len(content),
            'pages_with_text': len(text_parts),
        }
        return True, content, metadata
    except pypdf.errors.PdfReadError:
        return False, "Invalid or corrupted PDF file.", {}
    except Exception as e:
        return False, f"Failed to read PDF file: {e}", {}


def read_image(file_path: str) -> Tuple[bool, str, Dict[str, Any]]:
    """Read image metadata and prepare for vision model processing (JPEG/PNG)."""
    try:
        with Image.open(file_path) as img:
            img.verify()

        with Image.open(file_path) as img:
            width, height = img.size
            mode = img.mode
            format_name = img.format
            mime_type = 'image/png' if format_name == 'PNG' else 'image/jpeg'

            metadata = {
                'type': 'png' if format_name == 'PNG' else 'jpeg',
                'size_bytes': os.path.getsize(file_path),
                'width': width,
                'height': height,
                'mode': mode,
                'format': format_name,
                'mime_type': mime_type,
                'path': os.path.abspath(file_path),
            }

        content = (
            f"[Attached Image: {os.path.basename(file_path)}]\n"
            f"Dimensions: {width}x{height} pixels\n"
            f"Color mode: {mode}\n"
            f"Format: {format_name}\n"
            f"File size: {metadata['size_bytes']:,} bytes\n"
            f"Note: This image requires a vision-capable model for content analysis."
        )

        return True, content, metadata
    except Exception as e:
        return False, f"Failed to read image file: {e}", {}


FILE_READERS = {
    'markdown': read_markdown,
    'pdf': read_pdf,
    'jpeg': read_image,
    'png': read_image,
}


def ingest_file(file_path: str) -> Dict[str, Any]:
    """
    Ingest a file into temporary attachment context.

    Returns a result dict with:
    - success: bool
    - message: str (user-facing message)
    - file_path: str (absolute path)
    - file_type: str
    - content: str (extracted text content)
    - metadata: dict
    - recommendation: str or None (e.g., markdown .BETTER suggestion)
    """
    valid, error_msg = validate_file_path(file_path)
    if not valid:
        return {
            'success': False,
            'message': error_msg,
            'file_path': file_path,
            'file_type': None,
            'content': '',
            'metadata': {},
            'recommendation': None,
        }

    abs_path = os.path.abspath(file_path)
    file_type = get_file_type(abs_path)
    if file_type is None:
        return {
            'success': False,
            'message': f"Unsupported file type",
            'file_path': abs_path,
            'file_type': None,
            'content': '',
            'metadata': {},
            'recommendation': None,
        }

    reader = FILE_READERS.get(file_type)
    if not reader:
        return {
            'success': False,
            'message': f"No reader available for file type: {file_type}",
            'file_path': abs_path,
            'file_type': file_type,
            'content': '',
            'metadata': {},
            'recommendation': None,
        }

    success, content, metadata = reader(abs_path)
    if not success:
        return {
            'success': False,
            'message': content,
            'file_path': abs_path,
            'file_type': file_type,
            'content': '',
            'metadata': {},
            'recommendation': None,
        }

    attachment_data = {
        'file_path': abs_path,
        'file_name': os.path.basename(abs_path),
        'file_type': file_type,
        'content': content,
        'metadata': metadata,
        'attached_at': datetime.now().isoformat(),
    }
    _attachment_context[abs_path] = attachment_data

    recommendation = None
    if file_type == 'markdown':
        recommendation = (
            "File attached is a markdown file. I recommend using .BETTER for better results "
            "if the markdown file is a SKILLS/USER file that provides context, "
            "in-depth details or preferences for a task."
        )
    elif file_type in ('jpeg', 'png'):
        recommendation = (
            "An Image file was attached. I recommend that you use .VISION and follow up with a question, "
            "if you want to analyse this picture, or any other picture attached."
        )

    return {
        'success': True,
        'message': f"Successfully attached {file_type.upper()} file: {os.path.basename(abs_path)}",
        'file_path': abs_path,
        'file_type': file_type,
        'content': content,
        'metadata': metadata,
        'recommendation': recommendation,
    }


def format_attachment_summary(attachment: Dict[str, Any]) -> str:
    """Format a human-readable summary of an attachment."""
    meta = attachment['metadata']
    lines = [
        f"File: {attachment['file_name']}",
        f"Type: {attachment['file_type'].upper()}",
        f"Path: {attachment['file_path']}",
        f"Attached: {attachment['attached_at']}",
    ]

    if attachment['file_type'] == 'markdown':
        lines.append(f"Lines: {meta.get('line_count', 'N/A')}, Characters: {meta.get('char_count', 'N/A')}")
    elif attachment['file_type'] == 'pdf':
        lines.append(f"Pages: {meta.get('page_count', 'N/A')}, Pages with text: {meta.get('pages_with_text', 'N/A')}, Characters: {meta.get('char_count', 'N/A')}")
    elif attachment['file_type'] in ('jpeg', 'png'):
        lines.append(f"Dimensions: {meta.get('width', 'N/A')}x{meta.get('height', 'N/A')}, Mode: {meta.get('mode', 'N/A')}")

    lines.append(f"Size: {meta.get('size_bytes', 'N/A'):,} bytes")
    return "\n".join(lines)


def get_all_attachments() -> Dict[str, Dict[str, Any]]:
    """Get all current attachments."""
    return _attachment_context.copy()


def get_attachment(file_path: str) -> Optional[Dict[str, Any]]:
    """Get a specific attachment by absolute path."""
    abs_path = os.path.abspath(file_path)
    return _attachment_context.get(abs_path)


def has_attachments() -> bool:
    """Check if there are any active attachments."""
    return len(_attachment_context) > 0


def _format_attachments_context(attachments) -> str:
    """Build the standard ATTACHED FILES CONTEXT block from an iterable of attachment dicts."""
    if not attachments:
        return ""

    parts = ["=== ATTACHED FILES CONTEXT ==="]
    for attachment in attachments:
        parts.append(f"\n--- {attachment['file_name']} ({attachment['file_type'].upper()}) ---")
        parts.append(attachment['content'])
    parts.append("\n=== END ATTACHED FILES CONTEXT ===")
    return "\n".join(parts)


def get_combined_attachment_context() -> str:
    """
    Get all attachment content combined into a single context string
    for use by other Solaris components (like .BETTER).
    """
    return _format_attachments_context(_attachment_context.values())


def get_subset_attachment_context(indices: List[int]) -> str:
    """
    Get combined context for a subset of attachments by their 0-based insertion-order indices.
    Invalid indices are silently ignored. Returns empty string if no valid indices.
    """
    if not indices:
        return ""

    all_attachments = list(_attachment_context.values())
    selected = []
    for idx in indices:
        if 0 <= idx < len(all_attachments):
            selected.append(all_attachments[idx])

    return _format_attachments_context(selected)


def get_attachments_for_vision() -> List[Dict[str, Any]]:
    """
    Get attachments that are images, formatted for vision-capable models.
    Returns a list of dicts with 'path', 'mime_type', and 'metadata' for API calls.
    """
    vision_attachments = []
    for attachment in _attachment_context.values():
        if attachment['file_type'] in ('jpeg', 'png'):
            vision_attachments.append({
                'path': attachment['file_path'],
                'mime_type': attachment['metadata'].get('mime_type', 'image/jpeg'),
                'metadata': attachment['metadata'],
            })
    return vision_attachments


def get_subset_vision_attachments(indices: List[int]) -> List[Dict[str, Any]]:
    """
    Get vision-formatted attachments for a subset by 0-based insertion-order indices.
    Only includes image types (jpeg, png). Invalid indices ignored.
    """
    if not indices:
        return []

    all_attachments = list(_attachment_context.values())
    result = []
    for idx in indices:
        if 0 <= idx < len(all_attachments):
            att = all_attachments[idx]
            if att['file_type'] in ('jpeg', 'png'):
                result.append({
                    'path': att['file_path'],
                    'mime_type': att['metadata'].get('mime_type', 'image/jpeg'),
                    'metadata': att['metadata'],
                })
    return result