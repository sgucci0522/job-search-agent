import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
_service = None

# 結果シートの列定義
RESULT_COLUMNS = ['求人サイト', 'タイトル', '会社名', '勤務地', '雇用形態', '給与', 'URL', '取得日時', 'リモート判定', '応募状況']
COL_STATUS = 9  # J列（0始まり）= 応募状況


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


def get_search_config() -> dict:
    """検索条件シートからキーワードとフィルター条件を取得する。
    通常行はキーワード、「最低時給:1500」形式はフィルター条件として解釈する。"""
    result = get_service().spreadsheets().values().get(
        spreadsheetId=_get_spreadsheet_id(),
        range='検索条件!A2:A',
    ).execute()
    values = result.get('values', [])

    keywords = []
    min_hourly_wage = None

    for row in values:
        if not row:
            continue
        val = row[0].strip()
        if val.startswith('最低時給:'):
            raw = val.replace('最低時給:', '').replace('円', '').strip()
            try:
                min_hourly_wage = int(raw)
            except ValueError:
                print(f'警告: 最低時給の値が不正です → {val}')
        else:
            keywords.append(val)

    return {'keywords': keywords, 'min_hourly_wage': min_hourly_wage}


def ensure_result_header():
    get_service().spreadsheets().values().update(
        spreadsheetId=_get_spreadsheet_id(),
        range='結果!A1:J1',
        valueInputOption='RAW',
        body={'values': [RESULT_COLUMNS]},
    ).execute()


def _get_kept_rows() -> list[list]:
    """応募状況が入力済みの行を取得して保持する"""
    result = get_service().spreadsheets().values().get(
        spreadsheetId=_get_spreadsheet_id(),
        range='結果!A2:J',
    ).execute()
    rows = result.get('values', [])
    kept = []
    for row in rows:
        # J列（index 9）に値があれば保持
        if len(row) > COL_STATUS and row[COL_STATUS].strip():
            # 10列に満たない場合は空文字で埋める
            while len(row) < len(RESULT_COLUMNS):
                row.append('')
            kept.append(row)
    return kept


def write_results(jobs: list[dict]):
    sid = _get_spreadsheet_id()

    # 応募状況が入力済みの行を保持
    kept_rows = _get_kept_rows()

    # シートクリア
    get_service().spreadsheets().values().clear(
        spreadsheetId=sid,
        range='結果!A2:J',
    ).execute()

    # 応募状況保持行のURLセット（重複除外用）
    kept_urls = {row[6] for row in kept_rows if len(row) > 6 and row[6]}

    new_rows = [
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
            '',  # 応募状況（空欄）
        ]
        for job in jobs
        if job.get('url') not in kept_urls  # 応募状況保持済みURLは除外
    ]

    all_rows = kept_rows + new_rows

    if all_rows:
        get_service().spreadsheets().values().update(
            spreadsheetId=sid,
            range='結果!A2',
            valueInputOption='RAW',
            body={'values': all_rows},
        ).execute()

    skipped = len(jobs) - len(new_rows)
    print(f'新着 {len(new_rows)}件 / 応募状況保持 {len(kept_rows)}件 / 重複スキップ {skipped}件 を書き込みました')
