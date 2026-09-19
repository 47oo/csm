/* Optional real-browser check; does not add Playwright to application dependencies.
 * Requires an existing Playwright installation and Chromium. See
 * docs/test-reports/ui-visual-polish.md for invocation and coverage.
 * Only logs in and reads resources; opens but never submits a registration dialog.
 */
const assert = require('node:assert/strict')
const fs = require('node:fs/promises')
const path = require('node:path')
const { chromium } = require(process.env.CSM_PLAYWRIGHT_MODULE || 'playwright')

async function main() {
  assert(process.env.CSM_UI_URL, 'Set CSM_UI_URL to the intended preview URL')
  assert(process.env.CSM_UI_USERNAME, 'Set CSM_UI_USERNAME')
  assert(process.env.CSM_UI_PASSWORD, 'Set CSM_UI_PASSWORD')
  const artifacts = process.env.CSM_UI_ARTIFACTS
  if (artifacts) await fs.mkdir(artifacts, { recursive: true })
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    const screenshot = async name => {
      if (artifacts) await page.screenshot({ path: path.join(artifacts, name + '.png'), fullPage: true })
    }
    const noOverflow = async label => {
      const dimensions = await page.evaluate(() => ({ width: innerWidth, content: document.documentElement.scrollWidth }))
      assert(dimensions.content <= dimensions.width, `${label}: ${JSON.stringify(dimensions)}`)
    }
    await page.goto(process.env.CSM_UI_URL)
    await page.locator('input[type=password]').waitFor()
    await screenshot('login')
    await page.getByPlaceholder('请输入用户名').fill(process.env.CSM_UI_USERNAME)
    await page.getByPlaceholder('请输入口令').fill(process.env.CSM_UI_PASSWORD)
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await page.getByTestId('nav-clusters').waitFor()
    await page.getByRole('button', { name: '详情', exact: true }).first().waitFor()
    await screenshot('desktop')

    let checks = 0
    for (const width of [1440, 1024, 768, 760, 390, 320]) {
      await page.setViewportSize({ width, height: 900 })
      for (const resource of ['clusters', 'bare-metals', 'virtual-machines', 'network-interfaces', 'ip-addresses', 'containers', 'services']) {
        await page.getByTestId('nav-' + resource).click()
        // Allow CSS layout and table ResizeObserver updates to settle.
        await page.waitForTimeout(350)
        await noOverflow(`${width}px ${resource}`)
        checks++
      }
    }
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 })
      await page.getByTestId('nav-clusters').click()
      await page.getByRole('button', { name: '详情', exact: true }).first().waitFor()
      await screenshot(`mobile-${width}`)
      await page.getByRole('button', { name: '登记集群', exact: true }).click()
      await page.locator('.el-dialog').waitFor()
      await page.waitForTimeout(350)
      const dialog = await page.locator('.el-dialog').boundingBox()
      assert(dialog.width <= width - 32 && dialog.x >= 0, `${width}px dialog overflow`)
      await screenshot(`dialog-${width}`)
      await page.getByRole('button', { name: '取消', exact: true }).click()
      await page.getByRole('button', { name: '详情', exact: true }).first().click()
      await page.waitForTimeout(350)
      await noOverflow(`${width}px detail`)
      await screenshot(`detail-${width}`)
      await page.getByTestId('shell-search-cluster').click()
      await page.getByRole('option').first().click()
      await page.getByTestId('shell-search-keyword').fill('zzzz-ui-layout-no-match-5d821')
      await page.getByTestId('shell-search').click()
      await page.getByText('无匹配结果', { exact: true }).waitFor()
      await page.waitForTimeout(400)
      await noOverflow(`${width}px search`)
      await screenshot(`search-${width}`)
      checks += 3
    }
    assert.deepEqual(errors, [], 'Unexpected browser JavaScript errors')
    console.log(`${checks} layout checks passed; no page errors; no resource writes`)
  } finally {
    await browser.close()
  }
}

main().catch(error => { console.error(error); process.exitCode = 1 })
