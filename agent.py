import os
import json
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


def _extract_jobs(scraped: dict, keywords: list[str]) -> list[dict]:
    if not scraped.get('content'):
        return []

    prompt = f"""以下は求人サイト「{scraped['site_name']}」から取得したテキストです。

このテキストから求人情報を抽出し、在宅・リモート・テレワークで働ける求人だけをフィルタリングしてください。

各求人を以下のキーを持つJSONオブジェクトで表してください：
- title: 求人タイトル
- company: 会社名
- location: 勤務地
- employment_type: 雇用形態
- salary: 給与・報酬（不明なら空文字）
- url: 求人URL（不明なら空文字）
- remote_judgment: リモート可と判断した理由（1行）

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


def process_all(scraped_list: list[dict], keywords: list[str]) -> list[dict]:
    all_jobs = []
    for scraped in scraped_list:
        print(f'  AI解析: {scraped["site_name"]}')
        jobs = _extract_jobs(scraped, keywords)
        print(f'    リモート求人: {len(jobs)}件')
        all_jobs.extend(jobs)
    return all_jobs
