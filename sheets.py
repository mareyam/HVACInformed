"""Shared Google Sheets helper for the scraper scripts.

Auth: a service account JSON key file, path given by the
GOOGLE_SERVICE_ACCOUNT_FILE env var (default "service_account.json").
Share the target spreadsheet with that service account's email
(client_email in the JSON file) so it can read/write it.

Target spreadsheet: set GOOGLE_SHEET_ID to the spreadsheet ID (the long
id in its URL: https://docs.google.com/spreadsheets/d/<THIS>/edit).
"""

import os

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SERVICE_ACCOUNT_FILE = os.environ.get(
    "GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json"
)
SHEET_ID = os.environ.get(
    "GOOGLE_SHEET_ID", "1hZmRS42I4ox1Ci1DsNF5OlEbG-1eJlFH4y8dxO872oI"
)


def get_client():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


def get_worksheet(sheet_name, headers):
    if not SHEET_ID:
        raise RuntimeError(
            "Set the GOOGLE_SHEET_ID environment variable to your spreadsheet's ID."
        )
    client = get_client()
    spreadsheet = client.open_by_key(SHEET_ID)
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=sheet_name, rows=1000, cols=len(headers)
        )
    worksheet.clear()
    worksheet.append_row(headers)
    return worksheet


def read_rows(sheet_name):
    if not SHEET_ID:
        raise RuntimeError(
            "Set the GOOGLE_SHEET_ID environment variable to your spreadsheet's ID."
        )
    client = get_client()
    spreadsheet = client.open_by_key(SHEET_ID)
    worksheet = spreadsheet.worksheet(sheet_name)
    return worksheet.get_all_records()
