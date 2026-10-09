const {test, expect} = require('@playwright/test');
const attack = '<img src=x onerror="window.__demoProbe=1">';

async function openDemo(page) {
  await page.goto('/');
  await expect(page.locator('#tool-select option')).not.toHaveCount(0);
  await expect(page.locator('#resources-table')).toContainText('memory://welcome-note');
}

test('resources and arithmetic work through the actual service', async ({page}) => {
  await openDemo(page);
  await page.locator('#refresh-resources').click();
  await expect(page.locator('#resources-table')).toContainText('memory://welcome-note');
  await page.locator('#tab-tools').click();
  await page.locator('#tool-select').selectOption({label: 'calculator'});
  await page.locator('#tool-params').fill('{"expression":"(2 + 3) * -4"}');
  await page.locator('#run-tool').click();
  await expect(page.locator('#tool-output')).toContainText('-20');
  const result = JSON.parse(await page.locator('#tool-output').textContent());
  expect(result.result.result).toBe(-20);
});

test('all three examples work through the actual service', async ({page}) => {
  await page.goto('/examples.html');
  await expect(page.locator('#btn-echo')).toBeEnabled();
  await page.locator('#btn-echo').click();
  await expect(page.locator('#output')).toContainText('Hello');
  await page.locator('#btn-calc').click();
  await expect(page.locator('#output')).toContainText('"result": 4');
  await page.locator('#btn-weather').click();
  await expect(page.locator('#output')).toContainText('London');
  expect(JSON.parse(await page.locator('#output').textContent()).result).toHaveProperty('temperature_c');
});

test('chat displays HTML-like text without executing it', async ({page}) => {
  await openDemo(page);
  await page.locator('#tab-chat').click();
  await page.locator('#chat-input').fill(attack);
  await page.locator('#chat-input').press('Enter');
  await expect(page.locator('#chat-window')).toContainText(attack);
  await expect(page.locator('#chat-window > div')).toHaveCount(2);
  await expect(page.locator('#chat-window img')).toHaveCount(0);
  expect(await page.evaluate(() => window.__demoProbe || 0)).toBe(0);
  await expect(page.locator('#chat-input')).toHaveValue('');
});

test('resource descriptions also render as text', async ({page}) => {
  await page.route('**/v1/resources', route => route.fulfill({
    json: [{uri: 'memory://test', description: attack}]
  }));
  await page.goto('/');
  await expect(page.locator('#resources-table')).toContainText(attack);
  await expect(page.locator('#resources-table img')).toHaveCount(0);
  expect(await page.evaluate(() => window.__demoProbe || 0)).toBe(0);
});

test('invalid parameters do not dispatch an invocation', async ({page}) => {
  await openDemo(page);
  let invocations = 0;
  page.on('request', request => {if (request.url().endsWith('/invoke')) invocations++;});
  await page.locator('#tab-tools').click();
  await page.locator('#tool-params').fill('{"expression":');
  await page.locator('#run-tool').click();
  await expect(page.locator('#tool-output')).toContainText('Use a JSON object');
  expect(invocations).toBe(0);
});

test('tool HTTP failure is visible and can be retried', async ({page}) => {
  let first = true;
  await page.route('**/v1/tool/*/invoke', route => {
    if (first) {first = false; return route.fulfill({status: 503, json: {detail: 'Temporarily unavailable'}});}
    return route.continue();
  });
  await page.goto('/examples.html');
  await page.locator('#btn-echo').click();
  await expect(page.locator('#output')).toContainText('Temporarily unavailable');
  await expect(page.locator('#btn-echo')).toBeEnabled();
  await page.locator('#btn-echo').click();
  await expect(page.locator('#output')).toContainText('Hello');
});

test('network failure preserves a chat draft and retry adds one exchange', async ({page}) => {
  await openDemo(page);
  let first = true;
  await page.route('**/v1/tool/*/invoke', route => {
    if (first) {first = false; return route.abort('connectionreset');}
    return route.continue();
  });
  await page.locator('#tab-chat').click();
  await page.locator('#chat-input').fill('Retry this message');
  await page.locator('#send-chat').click();
  await expect(page.locator('#chat-status')).toContainText("Couldn't reach the server");
  await expect(page.locator('#chat-input')).toHaveValue('Retry this message');
  await expect(page.locator('#chat-window > div')).toHaveCount(0);
  await page.locator('#chat-input').press('Enter');
  await expect(page.locator('#chat-window > div')).toHaveCount(2);
  await expect(page.locator('#chat-input')).toHaveValue('');
});

test('a missing tool is disabled while available examples still work', async ({page}) => {
  await page.route('**/v1/tool', async route => {
    const response = await route.fetch();
    const data = await response.json();
    await route.fulfill({json: data.filter(item => Object.values(item)[0].name !== 'echo')});
  });
  await page.goto('/examples.html');
  await expect(page.locator('#output')).toContainText('Unavailable tools: echo');
  await expect(page.locator('#btn-echo')).toBeDisabled();
  await page.locator('#btn-calc').click();
  await expect(page.locator('#output')).toContainText('"result": 4');
});

test('failed discovery is recoverable without reloading the page', async ({page}) => {
  let first = true;
  await page.route('**/v1/tool', route => {
    if (first) {first = false; return route.fulfill({status: 502, json: {detail: 'Tool discovery failed'}});}
    return route.continue();
  });
  await page.goto('/examples.html');
  await expect(page.locator('#output')).toContainText('Tool discovery failed');
  await expect(page.locator('#btn-calc')).toBeDisabled();
  await page.locator('#refresh-examples').click();
  await page.locator('#btn-calc').click();
  await expect(page.locator('#output')).toContainText('"result": 4');
});

test('unreadable discovery responses are shown and controls recover', async ({page}) => {
  await page.route('**/v1/tool', route => route.fulfill({body: 'not JSON'}));
  await page.goto('/examples.html');
  await expect(page.locator('#output')).toContainText('unreadable response');
  await expect(page.locator('#refresh-examples')).toBeEnabled();
  await expect(page.locator('#btn-calc')).toBeDisabled();
});

test('JSON RPC errors do not appear as successful tool results', async ({page}) => {
  await page.route('**/v1/tool/*/invoke', route => route.fulfill({
    json: {jsonrpc: '2.0', id: 1, error: {code: -32602, message: 'Test tool rejected its input'}}
  }));
  await page.goto('/examples.html');
  await page.locator('#btn-echo').click();
  await expect(page.locator('#output')).toContainText('Request failed: Test tool rejected its input');
  await expect(page.locator('#btn-echo')).toBeEnabled();
});

test('pending examples prevent duplicate dispatch and unlock after completion', async ({page}) => {
  let release;
  const gate = new Promise(resolve => {release = resolve;});
  let requests = 0;
  await page.route('**/v1/tool/*/invoke', async route => {
    requests++;
    await gate;
    await route.continue();
  });
  await page.goto('/examples.html');
  await page.locator('#btn-echo').click();
  await expect(page.locator('#btn-echo')).toBeDisabled();
  await page.locator('#btn-echo').dispatchEvent('click');
  await expect(page.locator('#btn-calc')).toBeDisabled();
  release();
  await expect(page.locator('#output')).toContainText('Hello');
  await expect(page.locator('#btn-calc')).toBeEnabled();
  expect(requests).toBe(1);
});
