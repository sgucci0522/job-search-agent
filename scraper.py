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

ANTI_BOT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
Object.defineProperty(navigator, 'languages', { get: () => ['ja-JP', 'ja'] });
"""


async def _extract_indeed_content(page) -> str:
    """Indeed: 求人カードから data-jk を使った安定URLで構造化テキストを抽出"""
    jobs = await page.evaluate("""
        () => {
            const cards = document.querySelectorAll(
                '[data-jk], .job_seen_beacon, [data-testid="job-card"], .resultWithShelf'
            );
            return Array.from(cards).map(card => {
                const jk = card.getAttribute('data-jk') ||
                           (card.querySelector('[data-jk]') || {}).getAttribute('data-jk') || '';
                const titleEl = card.querySelector('h2 a, [data-testid="job-title"] a, .jcs-JobTitle a');
                const title = titleEl ? titleEl.innerText.trim() : '';
                // data-jk があれば viewjob URL を構築（広告トラッキングURLを避ける）
                const href = jk ? 'https://jp.indeed.com/viewjob?jk=' + jk
                                 : (titleEl ? titleEl.href : '');
                const company = (card.querySelector('.companyName, [data-testid="company-name"]') || {}).innerText || '';
                const location = (card.querySelector('.companyLocation, [data-testid="text-location"]') || {}).innerText || '';
                const salary = (card.querySelector('.salary-snippet, .metadata.salary-snippet-container, [data-testid="attribute_snippet_testid"]') || {}).innerText || '';
                const desc = (card.querySelector('.job-snippet, [data-testid="job-snippet"]') || {}).innerText || '';
                return { title, href, company, location, salary, desc };
            }).filter(j => j.title);
        }
    """)

    if not jobs:
        # フォールバック: ページテキスト + リンク一覧
        return await _extract_text_with_links(page, 'https://jp.indeed.com')

    lines = []
    for job in jobs:
        lines.append(
            f"タイトル: {job.get('title', '')}\n"
            f"会社: {job.get('company', '')}\n"
            f"場所: {job.get('location', '')}\n"
            f"給与: {job.get('salary', '')}\n"
            f"説明: {job.get('desc', '')[:200]}\n"
            f"URL: {job.get('href', '')}\n---"
        )
    return '\n'.join(lines)


async def _extract_text_with_links(page, base_url: str = '') -> str:
    """ページテキスト + 数字IDで終わる求人リンク一覧を返す"""
    text = await page.inner_text('body')

    # 数字IDで終わるURLのみ抽出（カテゴリ・ナビリンクを除外）
    links = await page.evaluate("""
        () => {
            return Array.from(document.querySelectorAll('a[href]'))
                .filter(a => {
                    const href = a.href || '';
                    const label = a.innerText.trim();
                    // 5桁以上の数字IDで終わり、求人パスを含み、非求人URLを除外
                    return /\\/\\d{5,}$/.test(href) &&
                           /\\/(jobs?|offers?|works?|recruit|kyujin)\\//i.test(href) &&
                           !/\\/(category|group|search|tag|page|type|employer|company|profile|user)\\//i.test(href) &&
                           label.length > 2 && label.length < 120;
                })
                .map(a => ({ text: a.innerText.trim().replace(/\\s+/g, ' '), href: a.href }))
                .filter((v, i, arr) => arr.findIndex(x => x.href === v.href) === i) // 重複除去
                .slice(0, 60);
        }
    """)

    link_section = '\n'.join(f'{lk["text"]} → {lk["href"]}' for lk in links)
    return f'{text[:8000]}\n\n--- 実際の求人リンク（このURLのみ使用すること）---\n{link_section}'


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
                for sel in INDEED_JOB_SELECTORS:
                    try:
                        await page.wait_for_selector(sel, timeout=15000)
                        break
                    except Exception:
                        continue
                else:
                    await page.wait_for_timeout(5000)
                content = await _extract_indeed_content(page)
            else:
                await page.wait_for_timeout(3000)
                for selector in SEARCH_SELECTORS:
                    try:
                        element = await page.query_selector(selector)
                        if element and await element.is_visible():
                            await element.fill(keyword_str)
                            await page.keyboard.press('Enter')
                            await page.wait_for_load_state('networkidle', timeout=15000)
                            await page.wait_for_timeout(2000)
                            break
                    except Exception:
                        continue
                content = await _extract_text_with_links(page)

            return {
                'site_name': site_name,
                'content': content[:12000],
                'url': page.url,
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

            if result.get('content') and len(result['content']) >= 200:
                break

        if 'error' in result and not result.get('content'):
            print(f'    エラー: {result["error"]}')
        else:
            status = '検索あり' if result.get('searched') else '検索なし'
            print(f'    完了 ({status}, {len(result["content"])}文字取得)')

        results.append(result)
    return results
