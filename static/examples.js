document.addEventListener('DOMContentLoaded', () => {
  const api = window.MCPDemoAPI;
  const output = document.getElementById('output');
  const refresh = document.getElementById('refresh-examples');
  const examples = [
    {id: 'btn-echo', name: 'echo', params: {text: 'Hello'}},
    {id: 'btn-calc', name: 'calculator', params: {expression: '2 + 2'}},
    {id: 'btn-weather', name: 'weather.fake', params: {location: 'London'}}
  ];
  let tools = new Map();
  let busy = false;
  function updateButtons() {
    refresh.disabled = busy;
    for (const example of examples) {
      document.getElementById(example.id).disabled = busy || !tools.has(example.name);
    }
  }
  async function loadTools() {
    busy = true;
    tools.clear();
    output.textContent = 'Loading tools...';
    updateButtons();
    try {
      for (const [id, tool] of await api.tools()) tools.set(tool.name, id);
      const missing = examples.filter(example => !tools.has(example.name));
      output.textContent = missing.length ? 'Unavailable tools: ' + missing.map(item => item.name).join(', ') + '.' : '';
    } catch (error) {
      output.textContent = error.message;
    } finally {
      busy = false;
      updateButtons();
    }
  }
  for (const example of examples) {
    document.getElementById(example.id).addEventListener('click', async () => {
      if (busy || !tools.has(example.name)) return;
      busy = true;
      output.textContent = 'Running...';
      updateButtons();
      try {
        output.textContent = JSON.stringify(await api.invoke(tools.get(example.name), example.params), null, 2);
      } catch (error) {
        output.textContent = error.message;
      } finally {
        busy = false;
        updateButtons();
      }
    });
  }
  refresh.addEventListener('click', loadTools);
  loadTools();
});
