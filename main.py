from dotenv import load_dotenv
from sheets import get_job_sites, get_keywords, ensure_result_header, write_results
from scraper import scrape_all
from agent import process_all

load_dotenv()


def main():
    print('=== 求人エージェント 起動 ===')

    print('\n[1/4] Google Sheetsから設定を読み込み中...')
    sites = get_job_sites()
    keywords = get_keywords()

    if not sites:
        print('求人サイト一覧が空です。Google Sheetsの「求人サイト一覧」シートを確認してください。')
        return
    if not keywords:
        print('検索条件が空です。Google Sheetsの「検索条件」シートを確認してください。')
        return

    print(f'  求人サイト: {len(sites)}件')
    for s in sites:
        print(f'    - {s["name"]}: {s["url"]}')
    print(f'  検索キーワード: {keywords}')

    print('\n[2/4] 求人サイトをスクレイピング中...')
    scraped = scrape_all(sites, keywords)

    print('\n[3/4] AIで求人を解析・フィルタリング中...')
    jobs = process_all(scraped, keywords)

    print(f'\n合計 {len(jobs)}件のリモート求人が見つかりました')

    print('\n[4/4] 結果をGoogle Sheetsに書き込み中...')
    ensure_result_header()
    write_results(jobs)

    print('\n=== 完了 ===')


if __name__ == '__main__':
    main()
