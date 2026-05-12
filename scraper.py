import asyncio
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


async def _scrape(site_name: str, url: str, keywords: list[str]) -> dict:
    keyword_str = ' '.join(keywords)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            ),
            locale='ja-JP',
        )
        page = await context.new_page()

        try:
            await page.goto(url, timeout=60000, wait_until='domcontentloaded')
            # JS描画を待つ
            await page.wait_for_timeout(3000)

            searched = False
            for selector in SEARCH_SELECTORS:
                try:
                    element = await page.query_selector(selector)
                    if element and await element.is_visible():
                        await element.fill(keyword_str)
                        await page.keyboard.press('Enter')
                        await page.wait_for_load_state('networkidle', timeout=15000)
                        await page.wait_for_timeout(2000)
                        searched = True
                        break
                except Exception:
                    continue

            # ページ全体のテキストを取得
            content = await page.inner_text('body')

            # 取得量が少なすぎる場合はスクロールして再取得
            if len(content) < 500:
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(2000)
                content = await page.inner_text('body')

            return {
                'site_name': site_name,
                'content': content[:12000],
                'url': page.url,
                'searched': searched,
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
        result = asyncio.run(_scrape(site['name'], site['url'], keywords))
        if 'error' in result:
            print(f'    エラー: {result["error"]}')
        else:
            status = '検索あり' if result['searched'] else '検索なし'
            print(f'    完了 ({status}, {len(result["content"])}文字取得)')
        results.append(result)
    return results
