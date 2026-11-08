"""Audit release text for Cyrillic without extracting or modifying any input.

Default: scan package_release.collect_files(PROJECT).
Use --archive ZIP (repeatable) to scan archives instead. An explicit --project
PATH adds that project's release inputs even when --archive is also supplied.
Exit codes: 0 = automated text scan complete; 1 = Cyrillic found;
2 = incomplete automated coverage or an input error. Images always need a
separate visual review, including when the automated text scan exits with 0.
"""
from __future__ import annotations

import argparse
import html
import io
import json
from pathlib import Path, PurePosixPath
import sys
import unicodedata
import zipfile


# Keep the audit read-only, including imports of local and optional modules.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_release import PROJECT, collect_files


CYRILLIC_RANGES = (
    (0x0400, 0x052F), (0x1C80, 0x1C8F), (0x2DE0, 0x2DFF),
    (0xA640, 0xA69F), (0xFE2E, 0xFE2F), (0x1E030, 0x1E08F),
)
OFFICE_SUFFIXES = {".pptx", ".docx", ".xlsx", ".pptm", ".docm", ".xlsm"}
RASTER_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif",
                   ".tiff", ".ico", ".avif", ".emf", ".wmf"}
ENTITY_SUFFIXES = {".xml", ".rels", ".html", ".htm", ".xhtml", ".svg"}
TEXT_SUFFIXES = ENTITY_SUFFIXES | {
    ".json", ".jsonl", ".csv", ".tsv", ".txt", ".md", ".rst", ".py", ".js",
    ".ts", ".css", ".toml", ".yaml", ".yml", ".tex", ".bib", ".cls", ".sty",
    ".cfg", ".ini", ".sh", ".ps1", ".cff", ".sql", ".r", ".rmd",
}
LIMITATIONS = [
    "This detects Cyrillic code points, not every non-English language or translation error.",
    "No OCR or visual inspection is performed. Images and text drawn as paths need visual review.",
    "PDF coverage uses pypdf page text and document metadata; embedded images and attachments are not inspected.",
    "Office coverage scans all readable text members, including XML and embedded Office files; rendering is not checked.",
    "JSON and JSONL are parsed recursively; HTML/XML character references are decoded without fetching external entities.",
    "Other source-language escapes, custom XML entities, macros and unsupported binary formats are not interpreted.",
    "The default project scope is the release packager's allowlist, not every workspace file.",
]


def is_cyrillic(character):
    code = ord(character)
    if code < 0x0400:
        return False
    return (any(start <= code <= end for start, end in CYRILLIC_RANGES)
            or "CYRILLIC" in unicodedata.name(character, ""))


class Audit:
    def __init__(self, source):
        self.source = source
        self.counts = dict.fromkeys((
            "file_count", "nested_member_count", "text_count", "pdf_count",
            "pdf_page_count", "pdf_pages_with_extracted_text", "presentation_count",
            "word_document_count", "spreadsheet_count", "office_container_count",
        ), 0)
        self.findings = {}
        self.images = []
        self.unverified_binaries = []
        self.unverified_text = []
        self.pdf_pages_needing_visual_review = []
        self.errors = []

    def scan_text(self, name, text, view):
        positions = [index for index, char in enumerate(text) if is_cyrillic(char)]
        if not positions:
            return
        finding = self.findings.setdefault(name, {
            "file": name, "detected_views": [], "codepoints": set(), "examples": [],
        })
        finding["detected_views"].append({"view": view, "occurrences": len(positions)})
        finding["codepoints"].update(f"U+{ord(text[index]):04X}" for index in positions)
        for index in positions[:max(0, 5 - len(finding["examples"]))]:
            finding["examples"].append({
                "view": view,
                "line": text.count("\n", 0, index) + 1,
                "column": index - text.rfind("\n", 0, index),
                "excerpt": text[max(0, index - 35):index + 36],
            })

    def scan_decoded_string(self, name, text, view):
        self.scan_text(name, text, view)
        decoded = html.unescape(text)
        if decoded != text:
            self.scan_text(name, decoded, view + ":html_entities")

    def scan_json(self, name, value, location):
        if isinstance(value, str):
            self.scan_decoded_string(name, value, location)
        elif isinstance(value, dict):
            for key, child in value.items():
                self.scan_decoded_string(name, key, location + ":key")
                self.scan_json(name, child, location + "[" + json.dumps(key) + "]")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                self.scan_json(name, child, location + f"[{index}]")

    def scan_utf8(self, name, raw, suffix):
        try:
            # Office XML is normally UTF-8; also honor a UTF-16 byte-order mark.
            encoding = "utf-16" if suffix in ENTITY_SUFFIXES and raw.startswith(
                (b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
            text = raw.decode(encoding)
            if "\x00" in text:
                raise ValueError("NUL bytes indicate unsupported binary or text encoding")
        except (UnicodeError, ValueError) as exc:
            target = self.unverified_text if suffix in TEXT_SUFFIXES else self.unverified_binaries
            target.append({"file": name, "reason": str(exc)})
            return
        self.counts["text_count"] += 1
        self.scan_text(name, text, encoding)
        if suffix in ENTITY_SUFFIXES:
            decoded = html.unescape(text)
            if decoded != text:
                self.scan_text(name, decoded, "html_xml_entities")
        if suffix == ".json":
            try:
                self.scan_json(name, json.loads(text), "json:$")
            except (ValueError, RecursionError) as exc:
                self.unverified_text.append({"file": name, "reason": "JSON decoding: " + str(exc)})
        elif suffix == ".jsonl":
            for number, line in enumerate(text.splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    self.scan_json(name, json.loads(line), f"jsonl:line:{number}:$")
                except (ValueError, RecursionError) as exc:
                    self.unverified_text.append({
                        "file": name, "line": number, "reason": "JSONL decoding: " + str(exc),
                    })

    def scan_pdf(self, name, raw):
        self.counts["pdf_count"] += 1
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            self.unverified_binaries.append({"file": name, "reason": "pypdf unavailable: " + str(exc)})
            return
        try:
            reader = PdfReader(io.BytesIO(raw))
            if reader.is_encrypted and not reader.decrypt(""):
                raise ValueError("Encrypted PDF requires a password")
            for key, value in (reader.metadata or {}).items():
                self.scan_decoded_string(name, str(value), "pdf_metadata:" + str(key))
            for number, page in enumerate(reader.pages, 1):
                self.counts["pdf_page_count"] += 1
                try:
                    text = page.extract_text() or ""
                    self.scan_text(name, text, f"pdf_page:{number}")
                    if text.strip():
                        self.counts["pdf_pages_with_extracted_text"] += 1
                    else:
                        self.pdf_pages_needing_visual_review.append({
                            "file": name, "page": number, "reason": "No extractable text; no OCR performed",
                        })
                except Exception as exc:
                    self.unverified_binaries.append({
                        "file": name, "page": number, "reason": "PDF text extraction: " + str(exc),
                    })
        except Exception as exc:
            self.unverified_binaries.append({"file": name, "reason": "PDF parsing: " + str(exc)})

    def scan_office(self, name, raw, suffix, depth):
        self.counts["office_container_count"] += 1
        count = {".pptx": "presentation_count", ".pptm": "presentation_count",
                 ".docx": "word_document_count", ".docm": "word_document_count",
                 ".xlsx": "spreadsheet_count", ".xlsm": "spreadsheet_count"}[suffix]
        self.counts[count] += 1
        if depth >= 20:
            self.unverified_binaries.append({"file": name, "reason": "Nested Office depth exceeds 20"})
            return
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for entry in sorted(archive.infolist(), key=lambda item: item.filename):
                    if entry.is_dir():
                        continue
                    member = name + "!" + entry.filename
                    self.counts["nested_member_count"] += 1
                    try:
                        self.scan_file(member, archive.read(entry), depth + 1)
                    except Exception as exc:
                        self.unverified_binaries.append({"file": member, "reason": "Office member read: " + str(exc)})
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            self.unverified_binaries.append({"file": name, "reason": "Office container: " + str(exc)})

    def scan_file(self, name, raw, depth=0):
        self.scan_text(name, name, "member_name")
        suffix = PurePosixPath(name).suffix.lower()
        if suffix in RASTER_SUFFIXES or suffix == ".svg":
            self.images.append(name)
            if suffix != ".svg":
                return
        if suffix in OFFICE_SUFFIXES:
            self.scan_office(name, raw, suffix, depth)
        elif suffix == ".pdf":
            self.scan_pdf(name, raw)
        else:
            self.scan_utf8(name, raw, suffix)

    def scan_project(self, project):
        try:
            for name, raw in collect_files(project).items():
                self.counts["file_count"] += 1
                self.scan_file(name, raw)
        except Exception as exc:
            self.errors.append({"source": str(project), "reason": str(exc)})

    def scan_archive(self, path):
        try:
            with zipfile.ZipFile(path) as archive:
                for entry in sorted(archive.infolist(), key=lambda item: item.filename):
                    if entry.is_dir():
                        continue
                    self.counts["file_count"] += 1
                    try:
                        self.scan_file(entry.filename, archive.read(entry))
                    except Exception as exc:
                        self.errors.append({"file": entry.filename, "reason": "ZIP member read: " + str(exc)})
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            self.errors.append({"source": str(path), "reason": "ZIP open: " + str(exc)})

    def result(self):
        findings = []
        for name in sorted(self.findings):
            item = self.findings[name]
            findings.append({**item, "codepoints": sorted(item["codepoints"])})
        incomplete = bool(self.unverified_binaries or self.unverified_text or self.errors
                          or self.pdf_pages_needing_visual_review)
        return {
            "source": self.source,
            "status": "cyrillic_found" if findings else "incomplete" if incomplete else "text_scan_passed",
            "automated_text_scan_complete": not incomplete,
            **self.counts,
            "finding_count": len(findings),
            "findings": findings,
            "image_count": len(self.images),
            "images_needing_visual_review": sorted(self.images),
            "pdf_pages_needing_visual_review": self.pdf_pages_needing_visual_review,
            "unverified_binaries": self.unverified_binaries,
            "unverified_text": self.unverified_text,
            "errors": self.errors,
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, action="append", default=[], metavar="ZIP",
                        help="Audit every non-directory ZIP member; may be repeated")
    parser.add_argument("--project", type=Path, metavar="PATH",
                        help="Audit this project's release allowlist, also when archives are supplied")
    args = parser.parse_args(argv)
    audits = []
    if args.project is not None or not args.archive:
        project = (args.project or PROJECT).resolve()
        audit = Audit({"kind": "project_release_allowlist", "path": str(project)})
        audit.scan_project(project)
        audits.append(audit.result())
    for archive in args.archive:
        path = archive.resolve()
        audit = Audit({"kind": "zip_archive", "path": str(path)})
        audit.scan_archive(path)
        audits.append(audit.result())
    has_cyrillic = any(result["finding_count"] for result in audits)
    complete = all(result["automated_text_scan_complete"] for result in audits)
    counts = {key: sum(result[key] for result in audits) for key in (
        "file_count", "nested_member_count", "text_count", "pdf_count", "pdf_page_count",
        "pdf_pages_with_extracted_text", "presentation_count", "word_document_count",
        "spreadsheet_count", "office_container_count", "finding_count", "image_count",
    )}
    result = {
        "schema_version": 1,
        "status": "cyrillic_found" if has_cyrillic else "incomplete" if not complete else "text_scan_passed",
        "automated_text_scan_complete": complete,
        "counts": counts,
        "count_conventions": {
            "file_count": "Non-directory release inputs or outer ZIP entries; repeated sources are counted separately.",
            "nested_member_count": "Members inside Office containers, including recursively embedded Office files.",
            "text_count": "Decoded text files, including Office XML; PDF pages and metadata are counted separately.",
            "finding_count": "Files or nested members containing detected Cyrillic; views may overlap.",
        },
        "audits": audits,
        "limitations": LIMITATIONS,
    }
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 1 if has_cyrillic else 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
