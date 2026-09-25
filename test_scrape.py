from playwright.sync_api import sync_playwright

def main():
    url = "https://www.iqair.com/us/usa/pennsylvania/altoona"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(2000)
        
        # Scroll down smoothly to trigger IntersectionObservers for lazy-loaded components
        for _ in range(10):
            page.keyboard.press("PageDown")
            page.wait_for_timeout(500)
        page.wait_for_timeout(1000)
        
        html = page.content()
        with open("dump.html", "w", encoding="utf-8") as f:
            f.write(html)
        browser.close()

if __name__ == "__main__":
    main()
