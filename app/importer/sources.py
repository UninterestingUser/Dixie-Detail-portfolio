"""Finding and reading the export files in the import folder.

Baserow's file names vary ("export - Customers.csv", "BaserowExport -
Customers - Grid.csv"), so each table is found by its name as a word in the
file name. Setmore's contact list is the CSV with "Setmore" in its name.
"""

import csv
import re

import yaml

BASEROW_TABLES = {
    "Customers": ["id", "Name", "First Name", "Last Name", "Phone", "Email", "Address", "City", "State", "ZIP",
                  "Vehicles", "Created on", "Last modified", "Autonumber", "Appointments"],
    "Vehicles": ["id", "Vehicle", "Year", "Make", "Model", "Vehicle Type", "Seating", "Color", "Customer", "Appointments"],
    "Appointments": ["id", "Appointment", "Date", "Status", "Customer", "Vehicle", "Vehicle Type", "Service Name",
                     "Service Summary", "Promo Price", "List Price", "Promotion", "Promo Type", "Promo Value",
                     "Price Override", "Final Price", "Notes", "Bookkeeping", "Hours", "Staff", "Auto Promo",
                     "Wages Due", "Employees Paid", "Job Wage Rate", "Total Wages"],
    "Bookkeeping": ["id", "Name", "Appointment", "Invoice", "Customer Paid", "Tip", "Payment Method", "Date",
                    "Customer", "Staff", "Wages Due", "Wage Override", "Profit"],
}
SETMORE_COLUMNS = ["Name", "Email", "Email1", "Phone", "Phone1", "Company", "Address", "Notes"]
CORRECTIONS_FILE = "import-corrections.yaml"


class SourceError(Exception):
    """The import folder is missing a file, has two candidates, or a file has the wrong columns."""


def find_file(folder, pattern, label):
    matches = sorted(path for path in folder.iterdir() if path.is_file() and pattern.search(path.name))
    if not matches:
        raise SourceError(f"No {label} file in {folder}.")
    if len(matches) > 1:
        raise SourceError(f"More than one {label} file in {folder}: {', '.join(p.name for p in matches)}.")
    return matches[0]


def read_csv(path, columns):
    # utf-8-sig drops the byte-order mark Baserow and Setmore write.
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        missing = [name for name in columns if name not in (reader.fieldnames or [])]
        if missing:
            raise SourceError(f"{path.name} is missing the column(s) {', '.join(missing)}.")
        return list(reader)


def load(folder):
    """Every table's rows, the Setmore contacts, the corrections, and the file names used."""
    if not folder.is_dir():
        raise SourceError(f"{folder} is not a folder.")
    tables, files = {}, {}
    for table, columns in BASEROW_TABLES.items():
        path = find_file(
            folder, re.compile(rf"(^|[^A-Za-z]){table}(?![A-Za-z]).*\.csv$", re.IGNORECASE), f"Baserow {table}"
        )
        tables[table] = read_csv(path, columns)
        files[table] = path.name
    setmore = find_file(folder, re.compile(r"setmore.*\.csv$", re.IGNORECASE), "Setmore contacts")
    tables["Setmore"] = read_csv(setmore, SETMORE_COLUMNS)
    files["Setmore"] = setmore.name
    corrections_path = folder / CORRECTIONS_FILE
    if not corrections_path.is_file():
        raise SourceError(f"No {CORRECTIONS_FILE} in {folder}.")
    corrections = yaml.safe_load(corrections_path.read_text()) or {}
    files["Corrections"] = CORRECTIONS_FILE
    return tables, corrections, files
