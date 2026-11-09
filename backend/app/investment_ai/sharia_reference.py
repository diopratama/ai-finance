"""Loader for the manually maintained ISSI reference supplied with the repository."""

import csv
import json
import os
import re
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


SOURCE_FILENAME = "Daftar Saham Syariah tercatat di Bursa Efek Indonesia 110826.xlsx - Saham Syariah di BEI.csv"
_lock = threading.Lock()
_cache_signature: Optional[tuple[str, int, int, str, int, int]] = None
_cache_value: Optional[Dict[str, Any]] = None


class ShariaReferenceError(ValueError):
    """Raised when the supplied ISSI reference cannot be safely parsed."""


def _paths() -> tuple[Path, Optional[Path]]:
    app_dir = Path(__file__).resolve().parent.parent
    backend_dir = app_dir.parent
    repo_dir = backend_dir.parent
    csv_override = os.getenv("ISSI_REFERENCE_PATH")
    metadata_override = os.getenv("ISSI_REFERENCE_METADATA_PATH")
    csv_candidates = [
        Path(csv_override).expanduser() if csv_override else None,
        Path("/app/data/issi_reference.csv"),
        backend_dir / "data" / "issi_reference.csv",
        repo_dir / SOURCE_FILENAME,
    ]
    metadata_candidates = [
        Path(metadata_override).expanduser() if metadata_override else None,
        Path("/app/data/issi_reference_metadata.json"),
        backend_dir / "data" / "issi_reference_metadata.json",
    ]
    csv_path = next((p for p in csv_candidates if p is not None and p.is_file()), None)
    metadata_path = next((p for p in metadata_candidates if p is not None and p.is_file()), None)
    if csv_path is None:
        raise ShariaReferenceError(
            "ISSI reference CSV not found. Package the supplied file or set ISSI_REFERENCE_PATH."
        )
    return csv_path, metadata_path


def _normalized_headers(headers: List[Optional[str]]) -> Dict[str, str]:
    return {
        re.sub(r"[^a-z0-9]", "", (header or "").lower()): header or ""
        for header in headers
    }


def _optional_date(value: Any, field: str) -> Optional[date]:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ShariaReferenceError(f"Invalid {field} date {value!r}; expected YYYY-MM-DD") from exc


def load_sharia_reference() -> Dict[str, Any]:
    """Loads, validates, and caches the CSV until its file signature changes."""
    global _cache_signature, _cache_value
    csv_path, metadata_path = _paths()
    csv_stat = csv_path.stat()
    metadata_stat = metadata_path.stat() if metadata_path else None
    signature = (
        str(csv_path),
        csv_stat.st_mtime_ns,
        csv_stat.st_size,
        str(metadata_path) if metadata_path else "",
        metadata_stat.st_mtime_ns if metadata_stat else 0,
        metadata_stat.st_size if metadata_stat else 0,
    )
    with _lock:
        if _cache_value is not None and signature == _cache_signature:
            return _cache_value

        metadata: Dict[str, Any] = {}
        if metadata_path:
            try:
                with metadata_path.open("r", encoding="utf-8") as stream:
                    metadata = json.load(stream)
            except (OSError, json.JSONDecodeError):
                # Metadata is informational; the manually maintained CSV is authoritative.
                metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}

        try:
            source_as_of = _optional_date(metadata.get("source_as_of"), "source_as_of")
            valid_until = _optional_date(metadata.get("valid_until"), "valid_until")
        except ShariaReferenceError:
            # Dates are informational only; invalid metadata must not disable the CSV list.
            source_as_of = valid_until = None

        issuers: List[Dict[str, Any]] = []
        seen_codes = set()
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                headers = _normalized_headers(reader.fieldnames or [])
                code_column = headers.get("kodesaham")
                name_column = headers.get("namapenerbitefek")
                issi_column = headers.get("issi")
                if not code_column or not name_column or not issi_column:
                    raise ShariaReferenceError(
                        "CSV must contain Kode Saham, Nama Penerbit Efek, and ISSI columns."
                    )
                for row_number, row in enumerate(reader, start=2):
                    code = re.sub(r"\s+", "", (row.get(code_column) or "")).upper()
                    name = re.sub(r"\s+", " ", (row.get(name_column) or "")).strip()
                    status = (row.get(issi_column) or "").strip().casefold()
                    if not code or not code.isalnum() or not name or status not in {"ya", "tidak"}:
                        raise ShariaReferenceError(f"Invalid issuer row {row_number}: code/name/status is invalid.")
                    if code in seen_codes:
                        raise ShariaReferenceError(f"Duplicate issuer ticker {code} in CSV.")
                    seen_codes.add(code)
                    issuers.append(
                        {
                            "code": code,
                            "ticker": f"{code}.JK",
                            "name": name,
                            "issi_status": "Ya" if status == "ya" else "Tidak",
                        }
                    )
        except OSError as exc:
            raise ShariaReferenceError(f"Cannot read ISSI CSV: {exc}") from exc

        if not issuers:
            raise ShariaReferenceError("ISSI reference CSV contains no issuer rows.")

        counts = {
            "Ya": sum(issuer["issi_status"] == "Ya" for issuer in issuers),
            "Tidak": sum(issuer["issi_status"] == "Tidak" for issuer in issuers),
        }
        _cache_value = {
            "source_name": metadata.get("source_name") or csv_path.stem,
            "source_file": csv_path.name,
            "source_as_of": source_as_of.isoformat() if source_as_of else None,
            "valid_until": valid_until.isoformat() if valid_until else None,
            "notes": metadata.get("notes", ""),
            "loaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "total": len(issuers),
            "counts": counts,
            "issuers": issuers,
            "by_ticker": {issuer["ticker"]: issuer for issuer in issuers},
        }
        _cache_signature = signature
        return _cache_value


def get_issi_universe() -> List[str]:
    """Returns only issuer tickers marked ISSI=Ya in the supplied reference."""
    reference = load_sharia_reference()
    return [issuer["ticker"] for issuer in reference["issuers"] if issuer["issi_status"] == "Ya"]


def get_issi_issuer(ticker: str) -> Optional[Dict[str, Any]]:
    """Returns the supplied reference entry for an IDX ticker, if present."""
    normalized = ticker.strip().upper()
    if not normalized.endswith(".JK"):
        normalized += ".JK"
    return load_sharia_reference()["by_ticker"].get(normalized)
