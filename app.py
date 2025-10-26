import io
from datetime import datetime
import streamlit as st
import pandas as pd
import gspread
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from gspread.exceptions import SpreadsheetNotFound
from google.oauth2.credentials import Credentials

# --- CONFIG ---
SHEET_NAME = "Receipt_Entries"
DRIVE_FOLDER_ID = "10oc7gQhwLPKCdU7XlxizhzztdY7SoPYi"

# --- Google OAuth setup ---
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets"
]

def get_credentials():
    """Authenticate via Streamlit Cloud secrets."""
    google_secrets = st.secrets["google"]

    creds = Credentials.from_authorized_user_info(
        {
            "client_id": google_secrets["client_id"],
            "client_secret": google_secrets["client_secret"],
            "refresh_token": google_secrets["refresh_token"],
            "token_uri": google_secrets["token_uri"],
            "type": google_secrets["type"],
        },
        SCOPES,
    )

    drive_service = build("drive", "v3", credentials=creds)
    gc = gspread.authorize(creds)
    sheet = gc.open(st.secrets["general"]["SHEET_NAME"]).sheet1
    return creds, drive_service, sheet

creds, drive_service, gc = get_credentials()

def get_or_create_sheet(gc):
    """Open the target sheet; create it if missing."""
    sheet_name = st.secrets["general"]["SHEET_NAME"]
    try:
        return gc.open(sheet_name).sheet1
    except gspread.SpreadsheetNotFound:
        sh = gc.create(sheet_name)
        sh.share(None, perm_type="anyone", role="reader")
        worksheet = sh.get_worksheet(0)
        worksheet.append_row(["Timestamp", "Date", "Amount", "Currency",
                              "Category", "Notes", "DriveLink"])
        return worksheet
        
sheet = get_or_create_sheet(gc)

# --- Setup connections ---
creds, drive_service, gc = get_credentials()
sheet = get_or_create_sheet(gc)

# --- Streamlit UI ---
st.set_page_config(page_title="Receipt Uploader", page_icon="📸", layout="centered")
st.title("📸 Receipt Uploader")
st.caption("Upload receipts (PDF or image) directly to Google Drive and record entries in Google Sheets.")

uploaded_file = st.file_uploader("Upload receipt (PDF or image)", type=["pdf", "png", "jpg", "jpeg"])

with st.form("receipt_form"):
    c1, c2 = st.columns(2)
    with c1:
        tx_date = st.date_input("Date", datetime.today())
        amount = st.text_input("Amount (e.g. 45.60)")
        currency = st.text_input("Currency", "USD")
    with c2:
        category = st.text_input("Category", "e.g. Travel, Meals, Office")
        notes = st.text_area("Notes (optional)")
    submitted = st.form_submit_button("💾 Save Entry")

def guess_mime_type(name: str) -> str:
    name = name.lower()
    if name.endswith(".pdf"): return "application/pdf"
    if name.endswith(".png"): return "image/png"
    if name.endswith(".jpg") or name.endswith(".jpeg"): return "image/jpeg"
    return "application/octet-stream"

def upload_to_drive(file_bytes: bytes, filename: str, mimetype: str) -> str:
    metadata = {"name": filename, "parents": [DRIVE_FOLDER_ID]}
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mimetype, resumable=False)
    created = drive_service.files().create(
        body=metadata, media_body=media, fields="id, webViewLink"
    ).execute()
    drive_service.permissions().create(
        fileId=created["id"], body={"role": "reader", "type": "anyone"}
    ).execute()
    return created["webViewLink"]

if submitted:
    if not amount or not category:
        st.error("Please enter at least an Amount and Category.")
    else:
        drive_link = ""
        if uploaded_file:
            file_bytes = uploaded_file.read()
            mimetype = guess_mime_type(uploaded_file.name)
            unique_name = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{uploaded_file.name}"
            drive_link = upload_to_drive(file_bytes, unique_name, mimetype)

        new_row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            str(tx_date),
            amount,
            currency,
            category,
            notes,
            drive_link,
        ]
        sheet.append_row(new_row)
        st.success("✅ Entry saved to Google Sheets!")
        st.dataframe(pd.DataFrame([new_row],
            columns=["Timestamp","Date","Amount","Currency",
                     "Category","Notes","DriveLink"]))
        if drive_link:

            st.link_button("Open uploaded file in Drive", drive_link)


