// As telas usam os mesmos endpoints PUT/DELETE disponíveis na API.
const feedback = document.getElementById('feedback');
function showError(message) {
  feedback.className = 'alert error';
  feedback.textContent = message;
  feedback.scrollIntoView({block: 'center'});
}
async function send(url, method, body) {
  const response = await fetch(url, {method, body, headers: {'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content, 'Accept': 'application/json'}});
  if (response.redirected) { window.location.assign(response.url); return false; }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || 'Não foi possível concluir. Recarregue a página e tente novamente.');
  }
  return true;
}
document.querySelectorAll('[data-delete]').forEach(button => button.addEventListener('click', async () => {
  if (!confirm('Excluir este registro? Esta ação remove o registro do sistema.')) return;
  button.disabled = true;
  try { if (await send(button.dataset.delete, 'DELETE')) { sessionStorage.setItem('agrosan-feedback', 'Registro excluído com sucesso.'); window.location.reload(); } }
  catch (error) { showError(error.message); }
  finally { button.disabled = false; }
}));
document.querySelectorAll('form[data-update]').forEach(form => form.addEventListener('submit', async event => {
  event.preventDefault();
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  try { if (await send(form.dataset.update, 'PUT', new FormData(form))) { sessionStorage.setItem('agrosan-feedback', 'Registro atualizado com sucesso.'); window.location.assign('/listagem'); } }
  catch (error) { showError(error.message); }
  finally { button.disabled = false; }
}));
const saved = sessionStorage.getItem('agrosan-feedback');
if (saved) { feedback.className = 'alert success'; feedback.textContent = saved; sessionStorage.removeItem('agrosan-feedback'); }
