document.addEventListener('DOMContentLoaded', () => {
  const api = window.MCPDemoAPI;
  const sections = {
    'tab-resources': document.getElementById('resources'),
    'tab-tools': document.getElementById('tools'),
    'tab-chat': document.getElementById('chat')
  };
  for (const id of Object.keys(sections)) {
    document.getElementById(id).addEventListener('click', () => {
      Object.values(sections).forEach(section => section.classList.add('hidden'));
      sections[id].classList.remove('hidden');
    });
  }
  const resourceStatus = document.getElementById('resource-status');
  const refreshResources = document.getElementById('refresh-resources');
  async function loadResources() {
    refreshResources.disabled = true;
    resourceStatus.textContent = 'Loading resources...';
    const tbody = document.querySelector('#resources-table tbody');
    tbody.replaceChildren();
    try {
      const resources = await api.request('/v1/resources');
      if (!Array.isArray(resources)) throw new Error('The resource list could not be read.');
      for (const resource of resources) {
        if (!resource || typeof resource.uri !== 'string' || typeof resource.description !== 'string') {
          throw new Error('The resource list could not be read.');
        }
        const row = document.createElement('tr');
        for (const value of [resource.uri, resource.description]) {
          const cell = document.createElement('td');
          cell.textContent = value;
          row.append(cell);
        }
        tbody.append(row);
      }
      resourceStatus.textContent = resources.length ? '' : 'No resources are available.';
    } catch (error) {
      resourceStatus.textContent = error.message;
    } finally {
      refreshResources.disabled = false;
    }
  }
  refreshResources.addEventListener('click', loadResources);
  const select = document.getElementById('tool-select');
  const toolOutput = document.getElementById('tool-output');
  const runTool = document.getElementById('run-tool');
  const refreshTools = document.getElementById('refresh-tools');
  const sendChat = document.getElementById('send-chat');
  const chatStatus = document.getElementById('chat-status');
  let echoId = null;
  let toolBusy = false;
  let chatBusy = false;
  let loadingTools = false;
  function updateButtons() {
    select.disabled = loadingTools || toolBusy;
    document.getElementById('tool-params').disabled = toolBusy;
    runTool.disabled = loadingTools || toolBusy || !select.value;
    refreshTools.disabled = loadingTools || toolBusy || chatBusy;
    sendChat.disabled = loadingTools || chatBusy || !echoId;
  }
  async function loadTools() {
    loadingTools = true;
    const selected = select.value;
    select.replaceChildren();
    echoId = null;
    toolOutput.textContent = 'Loading tools...';
    updateButtons();
    try {
      const tools = await api.tools();
      for (const [id, tool] of tools) {
        const option = document.createElement('option');
        option.value = id;
        option.textContent = tool.name;
        select.append(option);
        if (tool.name === 'echo') echoId = id;
      }
      if (tools.has(selected)) select.value = selected;
      toolOutput.textContent = tools.size ? '' : 'No tools are available.';
      chatStatus.textContent = echoId ? '' : 'The echo tool is not available.';
    } catch (error) {
      toolOutput.textContent = error.message;
      chatStatus.textContent = error.message;
    } finally {
      loadingTools = false;
      updateButtons();
    }
  }
  refreshTools.addEventListener('click', loadTools);
  runTool.addEventListener('click', async () => {
    if (toolBusy || loadingTools || !select.value) return;
    let params;
    try {
      params = JSON.parse(document.getElementById('tool-params').value);
      if (!params || typeof params !== 'object' || Array.isArray(params)) throw new Error();
    } catch {
      toolOutput.textContent = 'Use a JSON object for tool parameters.';
      return;
    }
    toolBusy = true;
    toolOutput.textContent = 'Running...';
    updateButtons();
    try {
      toolOutput.textContent = JSON.stringify(await api.invoke(select.value, params), null, 2);
    } catch (error) {
      toolOutput.textContent = error.message;
    } finally {
      toolBusy = false;
      updateButtons();
    }
  });
  const input = document.getElementById('chat-input');
  async function sendMessage() {
    if (chatBusy || loadingTools || !echoId || !input.value.trim()) return;
    const message = input.value;
    chatBusy = true;
    input.disabled = true;
    chatStatus.textContent = 'Sending...';
    updateButtons();
    try {
      const data = await api.invoke(echoId, {text: message});
      const chat = document.getElementById('chat-window');
      for (const [speaker, text] of [['You', message], ['Bot', JSON.stringify(data.result)]]) {
        const row = document.createElement('div');
        const label = document.createElement('strong');
        label.textContent = speaker + ': ';
        row.append(label, document.createTextNode(text));
        chat.append(row);
      }
      input.value = '';
      chatStatus.textContent = '';
      chat.scrollTop = chat.scrollHeight;
    } catch (error) {
      chatStatus.textContent = error.message;
    } finally {
      chatBusy = false;
      input.disabled = false;
      updateButtons();
      input.focus();
    }
  }
  sendChat.addEventListener('click', sendMessage);
  input.addEventListener('keydown', event => {
    if (event.key === 'Enter') { event.preventDefault(); sendMessage(); }
  });
  loadResources();
  loadTools();
});
