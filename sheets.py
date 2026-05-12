import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
_service = None


def get_service():
    global _service
    if _service:
        return _service

    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as f:
            f.write(creds.to_json())

    _service = build('sheets', 'v4', credentials=creds)
    return _service


def _get_spreadsheet_id():
    sid = os.getenv('SPREADSHEET_ID')
    if not sid:
        raise ValueError('.envにSPREADSHEET_IDが設定されていません')
    return sid


def get_job_sites() -> list[dict]:
    result = get_service().spreadsheets().values().get(
        spreadsheetId=_get_spreadsheet_id(),
        range='求人サイト一覧!A2:B',
    ).execute()
    values = result.get('values', [])
    return [{'name': row[0], 'url': row[1]} for row in values if len(row) >= 2]


def get_keywords() -> list[str]:
    result = get_service().spreadsheets().values().get(
        spreadsheetId=_get_spreadsheet_id(),
        range='検索条件!A2:A',
    ).execute()
    values = result.get('values', [])
    return [row[0] for row in values if row]


def ensure_result_header():
    headers = [['求人サイト', 'タイトル', '会社名', '勤務地', '雇用形態', '給与', 'URL', '取得日時', 'リモート判定']]
    get_service().spreadsheets().values().update(
        spreadsheetId=_get_spreadsheet_id(),
        range='結果!A1:I1',
        valueInputOption='RAW',
        body={'values': headers},
    ).execute()


def write_results(jobs: list[dict]):
    sid = _get_spreadsheet_id()
    get_service().spreadsheets().values().clear(
        spreadsheetId=sid,
        range='結果!A2:I',
    ).execute()

    if not jobs:
        print('書き込む求人がありません')
        return

    rows = [
        [
            job.get('site_name', ''),
            job.get('title', ''),
            job.get('company', ''),
            job.get('location', ''),
            job.get('employment_type', ''),
            job.get('salary', ''),
            job.get('url', ''),
            job.get('fetched_at', ''),
            job.get('remote_judgment', ''),
        ]
        for job in jobs
    ]

    get_service().spreadsheets().values().update(
        spreadsheetId=sid,
        range='結果!A2',
        valueInputOption='RAW',
        body={'values': rows},
    ).execute()
    print(f'{len(jobs)}件の求人を書き込みました')
