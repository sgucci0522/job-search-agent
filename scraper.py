import asyncio
import time
import random
from playwright.async_api import async_playwright

SEARCH_SELECTORS = [
    'input[type="search"]',
    'input[name="q"]',
    'input[name="keyword"]',
    'input[name="keywords"]',
    'input[id*="keyword"]',
    'input[placeholder*="キーワード"]',
    'input[placeholder*="検索"]',
    'input[placeholder*="職種"]',
    'input[placeholder*="求人"]',
]

INDEED_JOB_SELECTORS = [
    '.job_seen_beacon',
    '[data-testid="job-card"]',
    '.jobsearch-ResultsList li',
    '#mosaic-provider-jobcards',
]

# 募集終了を示す文言（個別ページで検出）
CLOSED_PATTERNS = [
    '募集終了', '応募受付終了', '受付終了', 'この仕事は終了',
    '応募を終了', '募集を終了', '募集期間が終了', 'この求人は終了',
    '応募受付を終了', '応募が終了', '終了しました', '募集は終了',
    'no longer available', 'job has expired', 'この求人情報は削除',
    '応募期間が過ぎ', 'この求人の掲載は終了',
]

ANTI_BOT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
Object.defineProperty(navigator, 'languages', { get: () => ['ja-JP', 'ja'] });
"""

MAX_JOBS_TO_VERIFY = 15  # 1サイトあたり最大確認件数


async def _is_active(page, url: str) -> bool:
    """個別求人ページを訪問して募集終了かチェック"""
    try:
        await page.goto(url, timeout=15000, wait_until='domcontentloaded')
        await page.wait_for_timeout(600)
        body = await page.inner_text('body')
        return not any(pat in body for pat in CLOSED_PATTERNS)
    except Exception:
        return True  # アクセス不能の場合は含める


async def _extract_candidate_links(page) -> list:
    """検索結果ページから求人候補リンクを抽出"""
    return await page.evaluate("""
        () => {
            const CLOSED = /募集終了|応募終了|受付終了|終了しました|クローズ/;
            return Array.from(document.querySelectorAll('a[href]'))
                .filter(a => {
                    const href = a.href || '';
                    const label = a.innerText.trim();
                    if (!/\\/\\d{5,}$/.test(href)) return false;
                    if (!/\\/(jobs?|offers?|works?|recruit|kyujin)\\//i.test(href)) return false;
                    if (/\\/(category|group|search|tag|page|type|employer|company|profile|user)\\//i.test(href)) return false;
                    if (label.length < 2 || label.length > 120) return false;
                    const card = a.closest('li, article, [class*="job"], [class*="card"], [class*="item"]') || a.parentElement;
                    if (card && CLOSED.test(card.innerText)) return false;
                    return true;
                })
                .map(a => ({ text: a.innerText.trim().replace(/\\s+/g, ' '), href: a.href }))
                .filter((v, i, arr) => arr.findIndex(x => x.href === v.href) === i)
                .slice(0, 30);
        }
    """)


async def _extract_indeed_jobs(page) -> list:
    """Indeed求人カードからURLを含む構造化データを抽出"""
    return await page.evaluate("""
        () => {
            const cards = document.querySelectorAll(
                '[data-jk], .job_seen_beacon, [data-testid="job-card"], .resultWithShelf'
            );
            return Array.from(cards).map(card => {
                const jk = card.getAttribute('data-jk') ||
                           (card.querySelector('[data-jk]') || {}).getAttribute('data-jk') || '';
                const titleEl = card.querySelector('h2 a, [data-testid="job-title"] a, .jcs-JobTitle a');
                const title = titleEl ? titleEl.innerText.trim() : '';
                const href = jk ? 'https://jp.indeed.com/viewjob?jk=' + jk
                                 : (titleEl ? titleEl.href : '');
                const company = (card.querySelector('.companyName, [data-testid="company-name"]') || {}).innerText || '';
                const location = (card.querySelector('.companyLocation, [data-testid="text-location"]') || {}).innerText || '';
                const salary = (card.querySelector('.salary-snippet, .metadata.salary-snippet-container, [data-testid="attribute_snippet_testid"]') || {}).innerText || '';
                const desc = (card.querySelector('.job-snippet, [data-testid="job-snippet"]') || {}).innerText || '';
                return { title, href, company, location, salary, desc };
            }).filter(j => j.title && j.href);
        }
    """)


async def _scrape(site_name: str, url: str, keywords: list[str], is_indeed: bool = False) -> dict:
    keyword_str = ' '.join(keywords)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled'],
        )
        context = await browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            ),
            locale='ja-JP',
            viewport={'width': 1280, 'height': 800},
        )
        await context.add_init_script(ANTI_BOT_SCRIPT)
        page = await context.new_page()

        try:
            await page.goto(url, timeout=60000, wait_until='domcontentloaded')

            if is_indeed:
                # Indeed: 求人カード描画を待機
                for sel in INDEED_JOB_SELECTORS:
                    try:
                        await page.wait_for_selector(sel, timeout=15000)
                        break
                    except Exception:
                        continue
                else:
                    await page.wait_for_timeout(5000)

                jobs = await _extract_indeed_jobs(page)
                jobs = [j for j in jobs if j.get('href')][:MAX_JOBS_TO_VERIFY]

                # 個別ページを訪問して募集終了を除外
                active_jobs = []
                for job in jobs:
                    ok = await _is_active(page, job['href'])
                    if ok:
                        active_jobs.append(job)
                    else:
                        print(f'      除外(募集終了): {job["title"][:30]}')

                lines = [
                    f"タイトル: {j.get('title','')}\n"
                    f"会社: {j.get('company','')}\n"
                    f"場所: {j.get('location','')}\n"
                    f"給与: {j.get('salary','')}\n"
                    f"説明: {j.get('desc','')[:200]}\n"
                    f"URL: {j.get('href','')}\n---"
                    for j in active_jobs
                ]
                content = '\n'.join(lines)

            else:
                await page.wait_for_timeout(3000)

                # 検索ボックスがあれば検索実行
                for selector in SEARCH_SELECTORS:
                    try:
                        el = await page.query_selector(selector)
                        if el and await el.is_visible():
                            await el.fill(keyword_str)
                            await page.keyboard.press('Enter')
                            await page.wait_for_load_state('networkidle', timeout=15000)
                            await page.wait_for_timeout(2000)
                            break
                    except Exception:
                        continue

                # 検索結果ページのテキストを先に保存
                search_text = await page.inner_text('body')

                # 候補リンクを抽出
                candidates = await _extract_candidate_links(page)
                candidates = candidates[:MAX_JOBS_TO_VERIFY]

                # 個別ページを訪問して募集終了を除外
                active_links = []
                for lk in candidates:
                    ok = await _is_active(page, lk['href'])
                    if ok:
                        active_links.append(lk)
                    else:
                        print(f'      除外(募集終了): {lk["text"][:30]}')

                link_section = '\n'.join(f'{lk["text"]} → {lk["href"]}' for lk in active_links)
                content = (
                    f'{search_text[:6000]}\n\n'
                    f'--- 募集中の求人リンク（このURLのみ使用すること）---\n'
                    f'{link_section}'
                )

            return {
                'site_name': site_name,
                'content': content[:12000],
                'url': url,
                'searched': True,
            }

        except Exception as e:
            return {
                'site_name': site_name,
                'content': '',
                'url': url,
                'searched': False,
                'error': str(e),
            }
        finally:
            await browser.close()


def scrape_all(sites: list[dict], keywords: list[str]) -> list[dict]:
    results = []
    for site in sites:
        print(f'  スクレイピング: {site["name"]} ({site["url"]})')
        is_indeed = 'indeed.com' in site['url']

        result = {'content': '', 'error': '未実行'}
        for attempt in range(3):
            if attempt > 0:
                wait = random.uniform(3, 6)
                print(f'    リトライ {attempt}/2 ({wait:.1f}秒待機)...')
                time.sleep(wait)

            result = asyncio.run(_scrape(site['name'], site['url'], keywords, is_indeed))

            if result.get('content') and len(result['content']) >= 100:
                break

        if 'error' in result and not result.get('content'):
            print(f'    エラー: {result["error"]}')
        else:
            print(f'    完了 ({len(result["content"])}文字取得)')

        results.append(result)
    return results
