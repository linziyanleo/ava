const { chromium } = require('playwright');

const URL = 'https://alidocs.dingtalk.com/i/nodes/vy20BglGWOxjGpq0C01qplYyVA7depqY?cid=28590804%3A5742472435&utm_source=im&utm_scene=team_space&iframeQuery=utm_medium%3Dim_card%26utm_source%3Dim&utm_medium=im_card&corpId=dingd8e1123006514592';

(async () => {
  try {
    // 连接已有 Chrome（remote debugging port 9222）
    const browser = await chromium.connectOverCDP('http://localhost:9222');
    const contexts = browser.contexts();
    const context = contexts[0] || await browser.newContext();
    const page = await context.newPage();

    process.stderr.write('[INFO] Navigating to alidocs...\n');
    await page.goto(URL, { waitUntil: 'networkidle', timeout: 30000 });
    const title = await page.title();
    process.stderr.write('[INFO] Page title: ' + title + '\n');

    // 等待文档内容加载
    await page.waitForTimeout(4000);

    // 尝试找到文档正文容器
    const content = await page.evaluate(() => {
      const selectors = [
        '.docs-editor-content',
        '.lake-editor',
        '.lake-content',
        '.doc-content',
        '.editor-container',
        '.document-content',
        '[class*="docContent"]',
        '[class*="editorContent"]',
        'article',
        '.main-content',
      ];
      
      for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el && el.innerText && el.innerText.trim().length > 200) {
          return { selector: sel, text: el.innerText.trim() };
        }
      }
      
      return { selector: 'body(fallback)', text: document.body.innerText.trim().slice(0, 8000) };
    });

    process.stdout.write(JSON.stringify(content, null, 2) + '\n');
    await browser.disconnect();
  } catch (e) {
    process.stderr.write('ERROR: ' + e.message + '\n' + e.stack + '\n');
    process.exit(1);
  }
})();
