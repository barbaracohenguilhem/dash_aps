#!/usr/bin/env python3
"""Pipeline de limpeza e padronização de texto dos arquivos CSV em data/parts/."""

import csv
import os
import re

csv.field_size_limit(10**7)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTS_DIR = os.path.join(ROOT_DIR, "data", "parts")
PART_FILES = [os.path.join(PARTS_DIR, f"dataset_part_0{i}.csv") for i in range(1, 6)]
OUTPUT_CSV = os.path.join(ROOT_DIR, "data", "jobs_cleaned.csv")

CP1252_FIXES = str.maketrans({
    "\x91": "'",
    "\x92": "'",
    "\x93": '"',
    "\x94": '"',
    "\x96": "-",
    "\x97": "-",
    "\x9f": "• ",
    "\xa0": " ",
    "\ufeff": "",
})

RE_URL_HASH = re.compile(r"(?:https?://[^\s#]*|www\.[^\s#]*)?#URL_[0-9a-fA-F]+#*")
RE_EMAIL_HASH = re.compile(r"(?:[^\s#@]+@)?#EMAIL_[0-9a-fA-F]+#*")
RE_PHONE_HASH = re.compile(r"#PHONE_[0-9a-fA-F]+#*")
RE_HTML_TAG = re.compile(r"</?(?:b|i|u|p|br|div|span|ul|ol|li|strong|em|h[1-6]|a|font|table|tr|td)\b[^>]*>", re.I)
RE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
RE_WHITESPACE = re.compile(r"\s+")


def clean_text(val: str) -> str:
    if not val:
        return ""
    if "\ufffd" in val:
        idx = val.find("\ufffd")
        sep = val.rfind("\n", 0, idx)
        val = val[:sep] if sep != -1 else val.replace("\ufffd", " ")

    val = val.translate(CP1252_FIXES)
    val = RE_CONTROL.sub(" ", val)
    val = RE_URL_HASH.sub("[URL]", val)
    val = RE_EMAIL_HASH.sub("[EMAIL]", val)
    val = RE_PHONE_HASH.sub("[TELEFONE]", val)
    val = RE_HTML_TAG.sub(" ", val)
    return RE_WHITESPACE.sub(" ", val).strip()


def main() -> None:
    unified_rows: list[list[str]] = []
    clean_headers: list[str] = []

    for filepath in PART_FILES:
        with open(filepath, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.reader(f)
            headers = [h.replace("\ufeff", "").strip() for h in next(reader)]
            if not clean_headers:
                clean_headers = headers

            part_rows = [[clean_text(cell) for cell in row] for row in reader]
            unified_rows.extend(part_rows)

        with open(filepath, "w", encoding="utf-8", newline="") as out_f:
            writer = csv.writer(out_f)
            writer.writerow(headers)
            writer.writerows(part_rows)

        print(f"[OK] {os.path.basename(filepath)}: {len(part_rows)} registros higienizados.")

    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as out_f:
        writer = csv.writer(out_f)
        writer.writerow(clean_headers)
        writer.writerows(unified_rows)

    print(f"[OK] {OUTPUT_CSV}: {len(unified_rows)} registros consolidados.")


if __name__ == "__main__":
    main()
