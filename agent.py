import os
import json
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


def _extract_jobs(scraped: dict, keywords: list[str], min_hourly_wage: int | None = None) -> list[dict]:
    if not scraped.get('content'):
        return []

    wage_condition = f'- 時給が{min_hourly_wage}円以上のもの\n' if min_hourly_wage else ''

    today = datetime.now().strftime('%Y-%m-%d')

    prompt = f"""以下は求人サイト「{scraped['site_name']}」から取得したテキストです。

本日の日付: {today}

このテキストから求人情報を抽出し、以下の条件でフィルタリングしてください：
【含める条件】
- 在宅・リモート・テレワークで働ける求人のみ
{wage_condition}
【除外する条件】
- 募集終了・応募締め切り・受付終了・クローズ・終了済みの求人は除外
- 「募集を終了」「応募受付終了」「この求人は終了」などの記載がある求人は除外
- 応募期限・締め切り日が本日（{today}）より前の求人は除外

各求人について以下の情報をJSON形式で返してください：
- title: 求人タイトル
- company: 会社名
- location: 勤務地
- employment_type: 雇用形態
- salary: 給与・報酬（不明なら空文字）
- deadline: 応募期限・締め切り日（YYYY-MM-DD形式。記載なければ空文字）
- url: 求人URL（テキスト末尾の「実際の求人リンク」欄にあるURLのみ使用。なければ空文字）
- remote_judgment: リモート可と判断した理由（1行）

【重要】urlは必ずテキスト中の「実際の求人リンク」欄に記載されたURLをそのままコピーしてください。
URLを推測・生成・変形しないでください。リンク欄にないURLは空文字にしてください。

必ず {{"jobs": [...]}} の形式のJSONのみを返してください。
求人が見つからない場合は {{"jobs": []}} を返してください。

サイトURL: {scraped['url']}
検索キーワード: {', '.join(keywords)}

テキスト:
{scraped['content']}
"""

    try:
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0,
            response_format={'type': 'json_object'},
        )
        data = json.loads(response.choices[0].message.content)
        jobs = data.get('jobs', [])

        fetched_at = datetime.now().strftime('%Y-%m-%d %H:%M')
        for job in jobs:
            job['site_name'] = scraped['site_name']
            job['fetched_at'] = fetched_at
            if not job.get('url'):
                job['url'] = scraped['url']

        return jobs
    except Exception as e:
        print(f'    OpenAIエラー: {e}')
        return []


def process_all(scraped_list: list[dict], keywords: list[str], min_hourly_wage: int | None = None) -> list[dict]:
    all_jobs = []
    for scraped in scraped_list:
        print(f'  AI解析: {scraped["site_name"]}')
        jobs = _extract_jobs(scraped, keywords, min_hourly_wage)
        print(f'    リモート求人: {len(jobs)}件')
        all_jobs.extend(jobs)
    return all_jobs
