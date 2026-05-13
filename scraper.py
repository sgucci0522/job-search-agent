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

# Indeed求人カードのセレクタ（いずれかが見つかれば描画完了）
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
                # Indeed: 求人カードが描画されるまで待機（最大15秒）
                for sel in INDEED_JOB_SELECTORS:
                    try:
                        await page.wait_for_selector(sel, timeout=15000)
                        break
                    except Exception:
                        continue
                else:
                    await page.wait_for_timeout(5000)
            else:
                await page.wait_for_timeout(3000)

                # 検索ボックスを探して検索実行
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

            content = await page.inner_text('body')

            # コンテンツ不足ならスクロールして再取得
            if len(content) < 500:
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(2000)
                content = await page.inner_text('body')

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

            if result.get('content') and len(result['content']) >= 500:
                break

        if 'error' in result and not result.get('content'):
            print(f'    エラー: {result["error"]}')
        else:
            status = '検索あり' if result.get('searched') else '検索なし'
            print(f'    完了 ({status}, {len(result["content"])}文字取得)')

        results.append(result)
    return results
