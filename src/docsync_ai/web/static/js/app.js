(() => {
  const form = document.querySelector('#analysis-form');
  const sourceInputs = document.querySelectorAll('input[name="input_source"]');
  const localFields = document.querySelector('#local-fields');
  const gitFields = document.querySelector('#git-fields');
  const demoFields = document.querySelector('#demo-fields');

  function updateSource() {
    const selected = document.querySelector('input[name="input_source"]:checked')?.value;
    localFields?.classList.toggle('hidden', selected !== 'local');
    gitFields?.classList.toggle('hidden', selected !== 'git');
    demoFields?.classList.toggle('hidden', selected !== 'demo');
  }
  sourceInputs.forEach((input) => input.addEventListener('change', updateSource));

  document.querySelector('#demo-button')?.addEventListener('click', (event) => {
    const demoRadio = document.querySelector('input[name="input_source"][value="demo"]');
    demoRadio.checked = true;
    updateSource();
    document.querySelector('#analysis-form')?.scrollIntoView({behavior: 'smooth', block: 'center'});
  });

  form?.addEventListener('submit', () => {
    const overlay = document.querySelector('#loading');
    const message = document.querySelector('#loading-message');
    const messages = [
      '正在读取项目……', '正在解析 Python……', '正在解析文档……',
      '正在分析配置……', '正在执行一致性检测……',
      '正在处理语义候选……', '正在生成报告……'
    ];
    let index = 0;
    overlay?.classList.remove('hidden');
    window.setInterval(() => {
      index = Math.min(index + 1, messages.length - 1);
      if (message) message.textContent = messages[index];
    }, 650);
  });

  const filters = ['severity-filter', 'rule-filter', 'status-filter']
    .map((id) => document.querySelector(`#${id}`)).filter(Boolean);
  function applyFilters() {
    const severity = document.querySelector('#severity-filter')?.value || 'all';
    const rule = document.querySelector('#rule-filter')?.value || 'all';
    const status = document.querySelector('#status-filter')?.value || 'all';
    let visible = 0;
    document.querySelectorAll('.result-item').forEach((item) => {
      const show = (severity === 'all' || item.dataset.severity === severity)
        && (rule === 'all' || item.dataset.rule === rule)
        && (status === 'all' || item.dataset.status === status);
      item.classList.toggle('hidden', !show);
      if (show) visible += 1;
    });
    const counter = document.querySelector('#visible-count');
    if (counter) counter.textContent = `显示 ${visible} 项`;
  }
  filters.forEach((filter) => filter.addEventListener('change', applyFilters));
  if (filters.length) applyFilters();

})();
