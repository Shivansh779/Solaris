import os

import pytest

from attachment import (
    SUPPORTED_EXTENSIONS,
    clear_attachment_context,
    format_attachment_summary,
    get_all_attachments,
    get_attachment,
    get_attachment_context,
    get_attachments_for_vision,
    get_combined_attachment_context,
    get_file_type,
    has_attachments,
    ingest_file,
    read_image,
    read_markdown,
    read_pdf,
    remove_attachment,
    validate_file_path,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MD = os.path.join(ROOT, "test_attach.md")
PDF = os.path.join(ROOT, "test_attach.pdf")
JPG = os.path.join(ROOT, "test_attach.jpg")


@pytest.fixture(autouse=True)
def _clean_context():
    clear_attachment_context()
    yield
    clear_attachment_context()


class TestFileType:
    def test_supported_extensions_table(self):
        assert SUPPORTED_EXTENSIONS == {
            ".md": "markdown",
            ".pdf": "pdf",
            ".jpg": "jpeg",
            ".jpeg": "jpeg",
            ".png": "png",
        }

    def test_known_extensions(self):
        assert get_file_type("a.md") == "markdown"
        assert get_file_type("a.pdf") == "pdf"
        assert get_file_type("a.jpg") == "jpeg"
        assert get_file_type("a.jpeg") == "jpeg"
        assert get_file_type("a.png") == "png"

    def test_case_insensitive_extension(self):
        assert get_file_type("A.PDF") == "pdf"
        assert get_file_type("B.JPG") == "jpeg"

    def test_unsupported_extensions(self):
        for name in ("a.txt", "a.py", "a", "a.tar.gz"):
            assert get_file_type(name) is None


class TestValidate:
    def test_empty_path(self):
        ok, msg = validate_file_path("")
        assert ok is False
        assert "No file path" in msg

    def test_relative_path_rejected(self):
        ok, msg = validate_file_path("test_attach.md")
        assert ok is False
        assert "absolute" in msg.lower()

    def test_missing_absolute_path(self):
        ok, msg = validate_file_path("/nonexistent/file.pdf")
        assert ok is False
        assert msg == "File not found: /nonexistent/file.pdf"

    def test_directory_rejected(self, tmp_path):
        ok, msg = validate_file_path(str(tmp_path))
        assert ok is False
        assert "not a file" in msg

    def test_unsupported_extension_rejected(self, tmp_path):
        f = tmp_path / "notes.txt"
        f.write_text("hello")
        ok, msg = validate_file_path(str(f))
        assert ok is False
        assert "Unsupported file type" in msg

    def test_real_fixtures_are_valid(self):
        for path in (MD, PDF, JPG):
            ok, msg = validate_file_path(path)
            assert ok, msg


class TestReaders:
    def test_read_markdown(self):
        ok, content, meta = read_markdown(MD)
        assert ok
        assert meta["type"] == "markdown"
        assert meta["size_bytes"] == os.path.getsize(MD)
        assert content.startswith("# Test Markdown File")

    def test_read_markdown_invalid_utf8(self, tmp_path):
        f = tmp_path / "bad.md"
        f.write_bytes(b"\xff\xfe\x00 not utf8")
        ok, msg, meta = read_markdown(str(f))
        assert ok is False
        assert "invalid UTF-8" in msg

    def test_read_markdown_empty(self, tmp_path):
        f = tmp_path / "empty.md"
        f.write_text("")
        ok, msg, meta = read_markdown(str(f))
        assert ok is False

    def test_read_pdf_missing(self, tmp_path):
        ok, msg, meta = read_pdf(str(tmp_path / "missing.pdf"))
        assert ok is False

    def test_read_pdf_empty(self, tmp_path):
        f = tmp_path / "empty.pdf"
        f.write_bytes(b"%PDF-1.4\n%%EOF\n")
        ok, msg, meta = read_pdf(str(f))
        assert isinstance(ok, bool)

    def test_read_pdf(self):
        ok, content, meta = read_pdf(PDF)
        assert ok
        assert meta["page_count"] == 2
        assert content.startswith("--- Page 1 ---")

    def test_read_image(self):
        ok, content, meta = read_image(JPG)
        assert ok
        assert meta["width"] == 800
        assert meta["height"] == 600
        assert meta["mime_type"] == "image/jpeg"


class TestIngest:
    def test_ingest_markdown(self):
        result = ingest_file(MD)
        assert result["success"], result["message"]
        assert result["file_type"] == "markdown"
        assert result["file_path"] == MD
        assert result["content"].startswith("# Test Markdown File")
        assert result["metadata"]["line_count"] > 1
        assert result["metadata"]["char_count"] == len(result["content"])
        assert result["metadata"]["size_bytes"] == os.path.getsize(MD)
        assert ".BETTER" in result["recommendation"]

    def test_ingest_pdf(self):
        result = ingest_file(PDF)
        assert result["success"], result["message"]
        assert result["file_type"] == "pdf"
        assert result["content"].startswith("--- Page 1 ---")
        assert result["metadata"]["page_count"] == 2

    def test_ingest_jpg(self):
        result = ingest_file(JPG)
        assert result["success"], result["message"]
        assert result["file_type"] == "jpeg"
        assert result["metadata"]["width"] == 800
        assert result["metadata"]["format"] == "JPEG"
        assert "Dimensions: 800x600" in result["content"]
        assert ".VISION" in result["recommendation"]

    def test_relative_path_rejected_at_ingest(self):
        result = ingest_file("test_attach.md")
        assert result["success"] is False
        assert "absolute" in result["message"].lower()
        assert not has_attachments()

    def test_unsupported_extension_rejected_at_ingest(self, tmp_path):
        f = tmp_path / "data.txt"
        f.write_text("hello")
        result = ingest_file(str(f))
        assert result["success"] is False
        assert "Unsupported file type" in result["message"]
        assert not has_attachments()

    def test_empty_markdown_rejected(self, tmp_path):
        f = tmp_path / "empty.md"
        f.write_text("\n")
        result = ingest_file(str(f))
        assert result["success"] is False
        assert "empty" in result["message"]

    def test_nonexistent_file_rejected(self):
        result = ingest_file("/nonexistent/file.md")
        assert result["success"] is False
        assert "not found" in result["message"].lower()
        assert not has_attachments()

    def test_corrupt_pdf_rejected(self, tmp_path):
        f = tmp_path / "broken.pdf"
        f.write_bytes(b"%PDF-1.7 garbage not really a pdf" * 10)
        result = ingest_file(str(f))
        assert result["success"] is False
        assert result["content"] == ""
        assert result["metadata"] == {}

    def test_broken_image_rejected(self, tmp_path):
        f = tmp_path / "evil.jpg"
        f.write_bytes(b"not an image at all")
        result = ingest_file(str(f))
        assert result["success"] is False

    def test_duplicate_ingest_keeps_single_entry(self):
        ingest_file(MD)
        ingest_file(MD)
        assert len(get_all_attachments()) == 1


class TestContext:
    @pytest.fixture(autouse=True)
    def _ingest_one(self):
        ingest_file(MD)
        yield

    def test_ingest_adds_to_context(self):
        ctx = get_attachment_context()
        assert MD in ctx
        assert ctx[MD]["file_name"] == "test_attach.md"

    def test_has_attachments(self):
        assert has_attachments() is True

    def test_clear_attachment_context(self):
        clear_attachment_context()
        assert not has_attachments()
        assert get_attachment_context() == {}

    def test_get_attachment_by_path(self):
        att = get_attachment(MD)
        assert att is not None
        assert att["file_type"] == "markdown"
        assert get_attachment("/nope/" + os.path.basename(MD)) is None

    def test_remove_attachment_by_index(self):
        removed = remove_attachment(0)
        assert removed is not None
        assert removed["file_path"] == MD
        assert not has_attachments()

    def test_remove_out_of_range(self):
        assert remove_attachment(1) is None
        assert remove_attachment(-1) is None

    def test_combined_context_block(self):
        combined = get_combined_attachment_context()
        assert "=== ATTACHED FILES CONTEXT ===" in combined
        assert "--- test_attach.md (MARKDOWN) ---" in combined
        assert "# Test Markdown File" in combined
        assert "=== END ATTACHED FILES CONTEXT ===" in combined

    def test_combined_context_empty(self):
        clear_attachment_context()
        assert get_combined_attachment_context() == ""

    def test_multiple_attachments(self):
        clear_attachment_context()
        ingest_file(MD)
        ingest_file(PDF)
        assert len(get_all_attachments()) == 2
        combined = get_combined_attachment_context()
        assert "test_attach.md" in combined
        assert "test_attach.pdf" in combined

    def test_get_all_attachments_is_snapshot(self):
        snap = get_all_attachments()
        clear_attachment_context()
        assert snap


class TestSummary:
    def test_markdown_summary(self):
        ingest_file(MD)
        s = format_attachment_summary(list(get_all_attachments().values())[0])
        assert "Type: MARKDOWN" in s
        assert "Lines:" in s

    def test_pdf_summary(self):
        ingest_file(PDF)
        s = format_attachment_summary(list(get_all_attachments().values())[0])
        assert "Type: PDF" in s
        assert "Pages:" in s

    def test_image_summary(self):
        ingest_file(JPG)
        s = format_attachment_summary(list(get_all_attachments().values())[0])
        assert "Type: JPEG" in s
        assert "Dimensions: 800x600" in s


class TestVisionPackaging:
    def test_only_images_returned_for_vision(self):
        ingest_file(MD)
        ingest_file(JPG)
        vis = get_attachments_for_vision()
        assert len(vis) == 1
        assert vis[0]["path"] == JPG
        assert vis[0]["mime_type"] == "image/jpeg"
        assert vis[0]["metadata"]["width"] == 800

    def test_no_attachments_for_vision(self):
        assert get_attachments_for_vision() == []