document.addEventListener('DOMContentLoaded', () => {
  const sections = {
    'tab-resources': document.getElementById('resources'),
    'tab-tools': document.getElementById('tools'),
    'tab-chat': document.getElementById('chat')
  };

  Object.keys(sections).forEach(btnId => {
    document.getElementById(btnId).addEventListener('click', () => {
      Object.values(sections).forEach(sec => sec.classList.add('hidden'));
      sections[btnId].classList.remove('hidden');
    });
  });

  async function loadResources() {
    const resp = await fetch('/v1/resources');
    const data = await resp.json();
    const tbody = document.querySelector('#resources-table tbody');
    tbody.innerHTML = '';
    data.forEach(r => {
      const row = document.createElement('tr');
      row.innerHTML = `<td>${r.uri}</td><td>${r.description}</td>`;
      tbody.appendChild(row);
    });
  }

  document.getElementById('refresh-resources').addEventListener('click', loadResources);
  loadResources();

  let tools = {};
  let echoId = null;
  async function loadTools() {
    const resp = await fetch('/v1/tool');
    const data = await resp.json();
    const select = document.getElementById('tool-select');
    select.innerHTML = '';
    data.forEach(item => {
      const id = Object.keys(item)[0];
      const t = item[id];
      tools[id] = t;
      const opt = document.createElement('option');
      opt.value = id;
      opt.textContent = t.name;
      select.appendChild(opt);
      if (t.name === 'echo' && !echoId) echoId = id;
    });
  }

  document.getElementById('run-tool').addEventListener('click', async () => {
    const toolId = document.getElementById('tool-select').value;
    let params = {};
    try { params = JSON.parse(document.getElementById('tool-params').value); } catch (e) {}
    const resp = await fetch(`/v1/tool/${toolId}/invoke`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: 1, method: 'invoke', params })
    });
    const data = await resp.json();
    document.getElementById('tool-output').textContent = JSON.stringify(data, null, 2);
  });

  document.getElementById('send-chat').addEventListener('click', async () => {
    const input = document.getElementById('chat-input');
    if (!echoId || !input.value) return;
    const msg = input.value;
    input.value = '';
    const resp = await fetch(`/v1/tool/${echoId}/invoke`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: 1, method: 'invoke', params: { text: msg } })
    });
    const data = await resp.json();
    const div = document.getElementById('chat-window');
    div.innerHTML += `<div><strong>You:</strong> ${msg}</div>`;
    div.innerHTML += `<div><strong>Bot:</strong> ${JSON.stringify(data.result)}</div>`;
    div.scrollTop = div.scrollHeight;
  });

  loadTools();
});
