const {defineConfig} = require('@playwright/test');
const port = Number(process.env.DEMO_TEST_PORT || 4010);
module.exports = defineConfig({
  testDir: './tests/browser',
  testMatch: '**/*.spec.cjs',
  timeout: 15000,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['json', {outputFile: 'test-results/browser-results.json'}]],
  use: {baseURL: `http://127.0.0.1:${port}`, trace: 'retain-on-failure', screenshot: 'only-on-failure'},
  webServer: {
    command: `python -m uvicorn server:app --host 127.0.0.1 --port ${port}`,
    url: `http://127.0.0.1:${port}/health`,
    reuseExistingServer: false,
    timeout: 30000,
    env: {OPENAI_API_KEY: '', ELEVENLABS_MCP_SECRET: 'local-browser-secret'}
  }
});
