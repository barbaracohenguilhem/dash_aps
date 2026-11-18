// Run against a local dashboard, never a production URL.
const assert = require("node:assert/strict");
const {chromium} = require("playwright");
const AxeBuilder = require("@axe-core/playwright").default;
const url = process.env.DASH_TEST_URL || "http://127.0.0.1:8050";
assert.ok(["localhost", "127.0.0.1"].includes(new URL(url).hostname), "Use a local test server");

(async function () {
  const browser = await chromium.launch({args: ["--no-sandbox"]});
  try {
    const context = await browser.newContext({viewport: {width: 1280, height: 800}});
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(url);
    await page.getByText("10.000 de 10.000 anúncios", {exact: true}).waitFor();

    async function labelsMatchRows() {
      await page.waitForFunction(() => {
        const radios = [...document.querySelectorAll('#tabela-vagas input[type="radio"]')];
        return radios.length && radios.every(input => {
          const row = input.closest("tr");
          return input.getAttribute("aria-label") === `Selecionar anúncio ${row.querySelector('td[data-dash-column="id_vaga"]').textContent.trim()}: ${row.querySelector('td[data-dash-column="title"]').textContent.trim()}`;
        });
      });
    }
    async function audit(state) {
      await labelsMatchRows();
      const results = await new AxeBuilder({page}).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
      assert.deepEqual(results.violations.map(v => ({id: v.id, targets: v.nodes.map(n => n.target)})), [], state);
      console.log(`axe: ${state} — no WCAG A/AA violations detected`);
    }
    await page.locator("#text-reading").filter({hasText: "mediana"}).waitFor();
    assert.equal(await page.locator(".population-tiles > span").count(), 100);
    assert.equal(await page.locator(".case-card").count(), 2);
    await page.locator(".text-alternative summary").click();
    assert.equal(await page.locator("#flow-table tbody tr").count(), 8);
    await page.locator(".case-card summary").first().click();
    await page.locator(".case-card details[open]").first().getByRole("heading", {name: "Descrição", exact: true}).waitFor();
    await page.locator(".case-card summary").first().click();
    await audit("initial desktop");
    assert.equal(await page.locator("html").getAttribute("lang"), "pt-BR");
    await page.locator("#f-busca").focus();
    await page.keyboard.press("Tab");
    assert.equal(await page.evaluate(() => document.activeElement.id), "f-status");
    await page.keyboard.press("Enter");
    await page.getByRole("option", {name: "Reais", exact: true}).waitFor();
    await page.keyboard.press("Escape");
    await page.locator("#f-status").focus();
    await page.keyboard.press("Tab");
    assert.equal(await page.evaluate(() => document.activeElement.id), "f-pais");
    await page.keyboard.press("Shift+Tab");
    assert.equal(await page.evaluate(() => document.activeElement.id), "f-status");

    await page.locator(".advanced-filters summary").click();
    await audit("expanded advanced filters");
    await page.getByRole("button", {name: "Próxima página de anúncios", exact: true}).click();
    await page.waitForFunction(() => document.querySelector('#tabela-vagas td[data-dash-column="id_vaga"]').textContent.trim() === "11");
    await audit("second page");
    const radio = page.locator('#tabela-vagas input[type="radio"]').first();
    await radio.focus();
    await page.keyboard.press("Space");
    await page.locator("#detalhe-vaga h3").filter({hasText: "#11"}).waitFor();
    await page.getByRole("button", {name: "Primeira página de anúncios", exact: true}).click();
    await page.locator('#tabela-vagas th.dash-header[data-dash-column="title"] .column-header--sort').click();
    await audit("sorted records");
    const toggle = page.getByRole("button", {name: "Distinguir maiúsculas e minúsculas na coluna Cargo", exact: true});
    await toggle.click();
    assert.equal(await toggle.getAttribute("aria-pressed"), "false");
    await page.getByRole("textbox", {name: "Filtrar coluna Cargo", exact: true}).fill("Marketing");
    await page.keyboard.press("Enter");
    await page.waitForFunction(() => [...document.querySelectorAll('#tabela-vagas td[data-dash-column="title"]')].every(td => td.textContent.toLowerCase().includes("marketing")));
    await audit("column-filtered records and insensitive toggle");
    await Promise.all([
      page.waitForResponse(response => response.url().includes("/_dash-update-component") && response.request().postDataJSON()?.changedPropIds?.includes("btn-reset-context.n_clicks") && response.status() === 200),
      page.locator("#btn-reset-context").click(),
    ]);
    await page.waitForFunction(() => document.querySelector('#tabela-vagas th.dash-filter[data-dash-column="title"] input[type="text"]').value === "");
    await page.locator("#f-busca").fill("no-such-job-xyz-831");
    await page.locator("#f-busca").press("Tab");
    await page.getByText("0 de 10.000 anúncios", {exact: true}).waitFor();
    const empty = await new AxeBuilder({page}).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    assert.deepEqual(empty.violations, [], "empty records");
    await page.locator("#btn-reset-context").click();
    await page.getByText("10.000 de 10.000 anúncios", {exact: true}).waitFor();
    await page.locator("#preset-logo").click();
    await page.locator("#active-filters").filter({hasText: "Logo: Não"}).waitFor();
    assert.ok(await page.locator('#tabela-vagas td[data-dash-column="tem_logo"]').evaluateAll(nodes => nodes.every(n => n.textContent === "Não")));
    await page.locator("#preset-remoto").click();
    await page.locator("#active-filters").filter({hasText: "Remoto: Sim"}).waitFor();
    assert.equal(await page.locator("#active-filters").getByText("Logo: Não", {exact: false}).count(), 0);
    await page.locator("#preset-fraude").click();
    await page.locator("#active-filters").filter({hasText: "Status: Fraudulenta"}).waitFor();
    await page.getByText("453 de 10.000 anúncios · Status filtrado", {exact: false}).waitFor();
    const workbook = page.getByRole("link", {name: "↓ Baixar dashboard Excel"});
    assert.match(await workbook.getAttribute("href"), /github\.com\/barbaracohenguilhem\/dash_aps\/blob\/[^/]+\/Jobs_Database\.xlsx\?raw=true/);
    await page.locator("#btn-reset-context").click();
    await page.getByText("10.000 de 10.000 anúncios", {exact: true}).waitFor();
    await page.locator('.atlas > summary').click();
    assert.equal(await page.locator(".atlas").getAttribute("open"), "");
    await page.locator("#g-setores .main-svg").first().waitFor();
    await page.locator('.atlas > summary').click();
    await page.locator('a[href="#setores"]').first().click();
    assert.equal(await page.locator(".atlas").getAttribute("open"), "");
    await page.setViewportSize({width: 390, height: 844});
    await audit("mobile after reset");
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), "no page-wide mobile overflow");
    assert.deepEqual(errors, [], "browser errors");
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
