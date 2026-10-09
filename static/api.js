window.MCPDemoAPI = {
  async request(path, options = {}) {
    let response;
    try {
      response = await fetch(path, options);
    } catch {
      throw new Error("Couldn't reach the server. Try again.");
    }
    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error(`The server returned an unreadable response (HTTP ${response.status}).`);
    }
    if (!response.ok) {
      const detail = typeof data.detail === 'string' ? data.detail : `HTTP ${response.status}`;
      throw new Error(`Request failed: ${detail}.`);
    }
    if (data?.error) {
      throw new Error(`Request failed: ${data.error.message || 'The tool returned an error'}.`);
    }
    return data;
  },
  async tools() {
    const data = await this.request('/v1/tool');
    if (!Array.isArray(data)) throw new Error('The tool list could not be read.');
    const tools = new Map();
    for (const item of data) {
      if (!item || typeof item !== 'object' || Array.isArray(item)) throw new Error('The tool list could not be read.');
      for (const [id, tool] of Object.entries(item)) {
        if (!tool || typeof tool.name !== 'string') throw new Error('The tool list could not be read.');
        tools.set(id, tool);
      }
    }
    return tools;
  },
  async invoke(id, params) {
    const data = await this.request(`/v1/tool/${encodeURIComponent(id)}/invoke`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id: 1, jsonrpc: '2.0', method: 'invoke', params})
    });
    if (!data || typeof data !== 'object' || !Object.hasOwn(data, 'result')) {
      throw new Error('The tool response could not be read.');
    }
    return data;
  }
};
