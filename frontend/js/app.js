import {api} from "./api.js";

const state = {
  user: null,
  appointments: [],
  selectedAppointment: null,
  financeReportPage: 1,
  financeReportPages: 1,
  patientFinanceId: null,
  editingUser: null,
  clinicalWorklist: [],
};
const byId = (id) => document.getElementById(id);
const money = (value) => new Intl.NumberFormat("pt-BR", {style: "currency", currency: "BRL"}).format(Number(value || 0));
const localDate = (value = new Date()) => {
  const offset = value.getTimezoneOffset() * 60000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 10);
};

function appendDescription(list, label, value) {
  const dt = document.createElement("dt"); const dd = document.createElement("dd");
  dt.textContent = label; dd.textContent = String(value); list.append(dt, dd);
}

function appendRow(body, values) {
  const row = document.createElement("tr");
  for (const value of values) { const cell = document.createElement("td"); cell.textContent = String(value); row.append(cell); }
  body.append(row);
  return row;
}

function displayDateTime(value) {
  if (!value) return "—";
  const [day, clock = ""] = value.split("T");
  return `${day.split("-").reverse().join("/")} ${clock.slice(0, 5)}`.trim();
}

function showToast(message, type = "success") {
  const toast = byId("toast");
  toast.textContent = message;
  toast.className = `toast ${type === "error" ? "error" : ""}`;
  toast.hidden = false;
  window.setTimeout(() => { toast.hidden = true; }, 4200);
}

function hasRole(...roles) { return roles.some((role) => state.user?.roles.includes(role)); }

function showView(id) {
  for (const view of ["login-view", "password-view", "app-view"]) byId(view).hidden = view !== id;
}

function applyPermissions() {
  document.querySelectorAll("[data-roles]").forEach((element) => {
    element.hidden = !element.dataset.roles.split(",").some((role) => hasRole(role));
  });
  document.querySelectorAll(".finance-only").forEach((element) => { element.hidden = !hasRole("gerente", "atendente"); });
  document.querySelectorAll(".restricted-write").forEach((element) => { element.hidden = !hasRole("gerente", "atendente"); });
}

async function establishSession(user) {
  state.user = user;
  byId("user-label").textContent = `${user.display_name} · ${user.roles.join(", ")}`;
  applyPermissions();
  showView("app-view");
  await refreshAll();
}

async function refreshAll() {
  await loadAppointments();
  if (hasRole("gerente", "atendente")) await loadFinance();
}

async function loadAppointments() {
  const loading = byId("appointments-loading");
  loading.hidden = false;
  try {
    const params = new URLSearchParams({page_size: "50"});
    const search = byId("appointment-search").value.trim();
    if (search) params.set("search", search);
    if (byId("filter-date-from").value) params.set("date_from", byId("filter-date-from").value);
    if (byId("filter-date-to").value) params.set("date_to", byId("filter-date-to").value);
    const result = await api(`/appointments?${params}`);
    state.appointments = result.items;
    byId("metric-appointments").textContent = String(result.total);
    const patientIds = [...new Set(result.items.map((item) => item.patient_id))];
    const patients = new Map();
    await Promise.all(patientIds.map(async (id) => {
      try { patients.set(id, await api(`/patients/${id}`)); } catch { patients.set(id, {name: `Paciente ${id}`}); }
    }));
    renderAppointments(result.items, patients);
  } finally { loading.hidden = true; }
}

function renderAppointments(items, patients) {
  const body = byId("appointments-body");
  body.replaceChildren();
  for (const item of items) {
    const row = document.createElement("tr");
    for (const value of [item.id, item.exam_date, patients.get(item.patient_id)?.name || "—", item.status, item.renach || "—"]) {
      const cell = document.createElement("td"); cell.textContent = String(value); row.append(cell);
    }
    const actions = document.createElement("td");
    const selectButton = document.createElement("button"); selectButton.type = "button"; selectButton.textContent = "Selecionar";
    selectButton.addEventListener("click", () => selectAppointment(item)); actions.append(selectButton);
    if (hasRole("gerente", "atendente") && item.status === "aberto") {
      const complete = document.createElement("button"); complete.type = "button"; complete.className = "secondary"; complete.textContent = "Concluir";
      complete.addEventListener("click", () => completeAppointment(item)); actions.append(complete);
    }
    row.append(actions); body.append(row);
  }
}

function selectAppointment(item) {
  state.selectedAppointment = item;
  byId("payment-appointment").value = item.id;
  byId("document-appointment").value = item.id;
  if (hasRole("gerente", "medico")) loadDocuments(item.id);
  showToast(`Atendimento ${item.id} selecionado`);
}

async function completeAppointment(item) {
  try {
    await api(`/appointments/${item.id}`, {method: "PUT", body: JSON.stringify({...item, status: "concluido", expected_version: item.row_version})});
    showToast("Atendimento concluído"); await loadAppointments();
  } catch (error) { showToast(error.message, "error"); }
}

async function loadFinance() {
  const summary = await api("/finance/summary");
  byId("metric-paid").textContent = money(summary.paid_total);
  byId("metric-payments").textContent = String(summary.paid_count);
  const list = byId("finance-summary"); list.replaceChildren();
  const values = [["Total", money(summary.paid_total)], ["Pagamentos", summary.paid_count], ["Estornos", summary.reversal_count]];
  for (const [label, value] of values) appendDescription(list, label, value);
  for (const [method, value] of Object.entries(summary.by_method)) appendDescription(list, method, money(value));
}

function setFinancePeriodDates() {
  const now = new Date(); const period = byId("finance-period").value;
  let from = new Date(now); let to = new Date(now);
  if (period === "monthly") from = new Date(now.getFullYear(), now.getMonth(), 1);
  if (period === "annual") from = new Date(now.getFullYear(), 0, 1);
  if (period !== "custom") {
    byId("finance-date-from").value = localDate(from);
    byId("finance-date-to").value = localDate(to);
  }
  const custom = period === "custom";
  byId("finance-date-from").disabled = !custom;
  byId("finance-date-to").disabled = !custom;
}

function financeReportParams(includePage = true) {
  const params = new URLSearchParams({
    date_from: byId("finance-date-from").value,
    date_to: byId("finance-date-to").value,
  });
  if (byId("finance-user").value) params.set("user_id", byId("finance-user").value);
  if (includePage) { params.set("page", String(state.financeReportPage)); params.set("page_size", "25"); }
  return params;
}

async function loadFinanceUsers() {
  if (!hasRole("gerente")) return;
  const users = await api("/admin/users");
  const select = byId("finance-user"); const selected = select.value;
  select.replaceChildren(new Option("Todos os usuários", ""));
  for (const user of users.items) select.append(new Option(`${user.display_name} (${user.username})`, String(user.id)));
  select.value = selected;
}

async function loadFinanceReport() {
  if (!hasRole("gerente")) return;
  const loading = byId("finance-report-loading"); loading.hidden = false;
  byId("finance-report-form").setAttribute("aria-busy", "true");
  try {
    const report = await api(`/finance/report?${financeReportParams()}`);
    byId("finance-total").textContent = money(report.summary.paid_total);
    byId("finance-count").textContent = String(report.summary.paid_count);
    byId("finance-average").textContent = money(report.summary.average_ticket);
    byId("finance-reversals").textContent = String(report.summary.reversal_count);

    const methods = byId("finance-methods"); methods.replaceChildren();
    const methodEntries = Object.entries(report.by_method);
    if (!methodEntries.length) appendDescription(methods, "Sem recebimentos", money(0));
    for (const [method, total] of methodEntries) appendDescription(methods, method, money(total));
    const comparison = byId("finance-comparison"); comparison.replaceChildren();
    appendDescription(comparison, "Pagamentos", money(report.comparison.payment_total));
    appendDescription(comparison, "Recibos", money(report.comparison.receipt_total));
    appendDescription(comparison, "Diferença", money(report.comparison.difference));

    const seriesBody = byId("finance-series-body"); seriesBody.replaceChildren();
    const maximum = Math.max(0, ...report.series.map((point) => Number(point.total)));
    for (const point of report.series) {
      const row = appendRow(seriesBody, [point.date.split("-").reverse().join("/"), point.count, money(point.total)]);
      const cell = document.createElement("td"); const progress = document.createElement("progress");
      progress.max = maximum || 1; progress.value = Number(point.total); progress.setAttribute("aria-label", `${money(point.total)} em ${point.date}`);
      cell.append(progress); row.append(cell);
    }
    if (!report.series.length) appendRow(seriesBody, ["Sem movimentações", "—", money(0), "—"]);

    const movements = byId("finance-movements-body"); movements.replaceChildren();
    for (const item of report.movements.items) appendRow(movements, [displayDateTime(item.paid_at), item.patient, item.user, item.methods.join(", ") || "—", item.status, money(item.total_amount)]);
    if (!report.movements.items.length) appendRow(movements, ["Sem movimentações", "—", "—", "—", "—", money(0)]);
    state.financeReportPages = report.movements.pages;
    byId("finance-movements-total").textContent = `${report.movements.total} movimentações`;
    byId("finance-page").textContent = `Página ${report.movements.page} de ${report.movements.pages}`;
    byId("finance-prev").disabled = report.movements.page <= 1;
    byId("finance-next").disabled = report.movements.page >= report.movements.pages;
  } finally {
    loading.hidden = true;
    byId("finance-report-form").removeAttribute("aria-busy");
  }
}

async function exportFinanceReport() {
  const response = await api(`/finance/report.csv?${financeReportParams(false)}`);
  const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a");
  link.href = url; link.download = "relatorio-financeiro.csv"; link.click(); URL.revokeObjectURL(url);
}

async function searchPatientFinance() {
  const search = byId("patient-finance-search").value.trim();
  const result = await api(`/patients?${new URLSearchParams({search, page_size: "20"})}`);
  const box = byId("patient-finance-results"); box.replaceChildren();
  if (!result.items.length) { const message = document.createElement("p"); message.textContent = "Nenhum paciente encontrado."; box.append(message); return; }
  for (const patient of result.items) {
    const button = document.createElement("button"); button.type = "button"; button.className = "search-result secondary";
    button.textContent = `${patient.name}${patient.cpf ? ` · CPF ${patient.cpf}` : ""}`;
    button.addEventListener("click", () => loadPatientFinance(patient.id).catch((error) => showToast(error.message, "error")));
    box.append(button);
  }
}

async function loadPatientFinance(patientId) {
  const report = await api(`/finance/patients/${patientId}/report`); state.patientFinanceId = patientId;
  byId("patient-finance-report").hidden = false;
  byId("patient-finance-name").textContent = report.patient.name;
  byId("patient-finance-identification").textContent = `Paciente ${report.patient.id}${report.patient.cpf ? ` · CPF ${report.patient.cpf}` : ""}`;
  byId("patient-charged").textContent = money(report.summary.charged_total);
  byId("patient-received").textContent = money(report.summary.received_total);
  byId("patient-pending").textContent = money(report.summary.pending_total);
  byId("patient-reversed").textContent = money(report.summary.reversed_total);

  const monthly = byId("patient-monthly-body"); monthly.replaceChildren();
  for (const item of report.monthly) appendRow(monthly, [item.month, money(item.payments), item.appointments, money(item.balance)]);
  if (!report.monthly.length) appendRow(monthly, ["Sem histórico", money(0), 0, money(0)]);
  const payments = byId("patient-payments-body"); payments.replaceChildren();
  for (const item of report.payments.items) appendRow(payments, [displayDateTime(item.paid_at), item.appointment_id, item.methods.join(", ") || "—", item.status, money(item.amount)]);
  if (!report.payments.items.length) appendRow(payments, ["Sem pagamentos", "—", "—", "—", money(0)]);
  const appointments = byId("patient-appointments-body"); appointments.replaceChildren();
  for (const item of report.appointments) appendRow(appointments, [item.id, item.date.split("-").reverse().join("/"), item.status]);
  if (!report.appointments.length) appendRow(appointments, ["—", "Sem atendimentos", "—"]);
  const receipts = byId("patient-receipts-body"); receipts.replaceChildren();
  for (const item of report.receipts) appendRow(receipts, [item.number, item.date.split("-").reverse().join("/"), money(item.amount)]);
  if (!report.receipts.length) appendRow(receipts, ["—", "Sem recibos", money(0)]);
  byId("patient-finance-report").scrollIntoView({behavior: "smooth", block: "start"});
}

async function exportPatientFinance() {
  if (!state.patientFinanceId) return;
  const response = await api(`/finance/patients/${state.patientFinanceId}/report.csv`);
  const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a");
  link.href = url; link.download = `financeiro-paciente-${state.patientFinanceId}.csv`; link.click(); URL.revokeObjectURL(url);
}

async function loadDocuments(appointmentId) {
  const result = await api(`/documents/appointments/${appointmentId}`);
  const list = byId("document-list"); list.replaceChildren();
  for (const item of result.items) {
    const row = document.createElement("div"); row.className = `document-row ${item.active ? "" : "inactive"}`;
    const label = document.createElement("span"); label.textContent = `${item.document_type} · versão ${item.version} · ${item.original_name}`;
    const button = document.createElement("button"); button.type = "button"; button.textContent = "Baixar"; button.addEventListener("click", () => downloadDocument(item));
    row.append(label, button); list.append(row);
  }
}

async function loadClinicalWorklist() {
  if (!hasRole("gerente", "medico")) return;
  const loading = byId("clinical-worklist-loading"); loading.hidden = false;
  try {
    const result = await api("/clinical/worklist"); state.clinicalWorklist = result.items;
    const body = byId("clinical-worklist-body"); body.replaceChildren();
    for (const item of result.items) {
      const row = appendRow(body, [item.appointment_id, item.patient_name, item.exam_date.split("-").reverse().join("/"), item.workflow_status]);
      const actions = document.createElement("td"); actions.className = "row-actions";
      const select = document.createElement("button"); select.type = "button"; select.className = "secondary"; select.textContent = "Selecionar";
      select.addEventListener("click", () => { byId("document-appointment").value = item.appointment_id; loadDocuments(item.appointment_id).catch((error) => showToast(error.message, "error")); });
      const reanalysis = document.createElement("button"); reanalysis.type = "button"; reanalysis.className = "secondary"; reanalysis.textContent = "Solicitar reanálise";
      reanalysis.addEventListener("click", () => requestReanalysis(item));
      actions.append(select, reanalysis); row.append(actions);
    }
    if (!result.items.length) appendRow(body, ["—", "Nenhum atendimento liberado", "—", "—", "—"]);
  } finally { loading.hidden = true; }
}

async function requestReanalysis(item) {
  const observation = window.prompt("Descreva obrigatoriamente o motivo da reanálise:");
  if (!observation?.trim()) return;
  try {
    await api(`/clinical/appointments/${item.appointment_id}/reanalysis`, {method: "POST", body: JSON.stringify({expected_version: item.row_version, observation: observation.trim()})});
    showToast("Reanálise registrada para o atendimento"); await loadClinicalWorklist();
  } catch (error) { showToast(error.message, "error"); }
}

async function loadDeliveryQueue() {
  if (!hasRole("gerente", "atendente")) return;
  const loading = byId("delivery-queue-loading"); loading.hidden = false;
  try {
    const result = await api("/documents/delivery/queue"); const body = byId("delivery-queue-body"); body.replaceChildren();
    for (const item of result.items) {
      const row = appendRow(body, [item.appointment_id, item.patient, item.kind === "reanalysis" ? item.observation : item.status, item.phone]);
      const actions = document.createElement("td"); actions.className = "delivery-actions";
      const channel = document.createElement("select"); channel.setAttribute("aria-label", `Canal do atendimento ${item.appointment_id}`);
      for (const [value, label] of [["telefone", "Telefone"], ["whatsapp_manual", "WhatsApp manual"], ["email_manual", "E-mail manual"], ["presencial", "Presencial"]]) { const option = document.createElement("option"); option.value = value; option.textContent = label; channel.append(option); }
      const deliver = document.createElement("button"); deliver.type = "button"; deliver.textContent = item.kind === "reanalysis" ? "Registrar contato" : "Registrar entrega";
      deliver.addEventListener("click", () => registerDelivery(item, channel.value)); actions.append(channel, deliver); row.append(actions);
    }
    if (!result.items.length) appendRow(body, ["—", "Fila vazia", "—", "—", "—"]);
  } finally { loading.hidden = true; }
}

async function registerDelivery(item, channel) {
  const result = window.prompt("Informe o resultado do contato ou entrega:");
  if (!result?.trim()) return;
  try {
    await api("/documents/delivery", {method: "POST", body: JSON.stringify({appointment_id: item.appointment_id, document_id: item.document_id, channel, result: result.trim()})});
    showToast("Registro de entrega salvo"); await loadDeliveryQueue();
  } catch (error) { showToast(error.message, "error"); }
}

async function loadUsers() {
  if (!hasRole("gerente")) return;
  const params = new URLSearchParams(); const search = byId("user-search").value.trim();
  if (search) params.set("q", search);
  const result = await api(`/admin/users${params.size ? `?${params}` : ""}`);
  const body = byId("users-body"); body.replaceChildren();
  for (const user of result.items) {
    const row = document.createElement("tr");
    for (const value of [user.username, user.display_name, user.roles.join(", "), user.active ? "Sim" : "Não", user.must_reset_password ? "Obrigatória" : "Concluída"]) {
      const cell = document.createElement("td"); cell.textContent = value; row.append(cell);
    }
    const actions = document.createElement("td"); actions.className = "row-actions";
    const edit = document.createElement("button"); edit.type = "button"; edit.className = "secondary"; edit.textContent = "Editar";
    edit.addEventListener("click", () => beginUserEdit(user)); actions.append(edit);
    const reset = document.createElement("button"); reset.type = "button"; reset.className = "secondary"; reset.textContent = "Redefinir senha";
    reset.addEventListener("click", () => resetUserPassword(user)); actions.append(reset);
    row.append(actions);
    body.append(row);
  }
  if (!result.items.length) appendRow(body, ["Nenhum usuário encontrado", "—", "—", "—", "—", "—"]);
}

function beginUserEdit(user) {
  state.editingUser = user;
  byId("new-username").value = user.username; byId("new-username").disabled = true;
  byId("new-display-name").value = user.display_name;
  byId("new-cpf").value = user.cpf || "";
  byId("new-birth-date").value = user.birth_date || "";
  byId("new-phone").value = user.phone || "";
  byId("new-email").value = user.email || "";
  byId("new-address").value = user.address || "";
  byId("new-role").value = user.roles[0];
  byId("new-professional-id").value = user.professional_id || "";
  byId("edit-active").checked = user.active;
  byId("edit-active-label").hidden = false; byId("user-cancel-edit").hidden = false;
  byId("user-submit").textContent = "Salvar usuário";
  syncProfessionalRequirement();
  byId("user-form").scrollIntoView({behavior: "smooth", block: "start"});
}

function clearUserForm() {
  state.editingUser = null; byId("user-form").reset(); byId("new-username").disabled = false;
  byId("edit-active-label").hidden = true; byId("user-cancel-edit").hidden = true;
  byId("user-submit").textContent = "Criar usuário";
  syncProfessionalRequirement();
}

function userPayload() {
  const professionalId = byId("new-professional-id").value;
  return {
    display_name: byId("new-display-name").value,
    cpf: byId("new-cpf").value,
    birth_date: byId("new-birth-date").value,
    phone: byId("new-phone").value,
    email: byId("new-email").value,
    address: byId("new-address").value,
    role: byId("new-role").value,
    professional_id: professionalId ? Number(professionalId) : null,
  };
}

function syncProfessionalRequirement() {
  const required = byId("new-role").value === "medico";
  byId("new-professional-id").required = required;
  byId("new-professional-id").setAttribute("aria-required", String(required));
}

async function resetUserPassword(user) {
  const result = await api(`/admin/users/${user.id}/reset-password`, {method: "POST"});
  byId("admin-result").textContent = `Senha temporária de ${user.username}: ${result.temporary_password}`;
  showToast("Senha redefinida; copie a senha temporária agora"); await loadUsers();
}

async function runReport() {
  const params = new URLSearchParams({date_from: byId("report-date-from").value, date_to: byId("report-date-to").value});
  if (byId("report-method").value) params.set("payment_method", byId("report-method").value);
  const [report, issues] = await Promise.all([api(`/reports/appointments?${params}`), api("/reports/migration-issues")]);
  const result = byId("report-result"); result.replaceChildren();
  for (const [label, value] of [["Período", `${report.filters.date_from} a ${report.filters.date_to}`], ["Atendimentos", report.appointment_count], ["Pacientes", report.patient_count], ["Total pago", money(report.paid_total)]]) {
    const dt = document.createElement("dt"); const dd = document.createElement("dd"); dt.textContent = label; dd.textContent = String(value); result.append(dt, dd);
  }
  const issueBox = byId("migration-issues"); issueBox.replaceChildren();
  const total = document.createElement("p"); total.textContent = `${issues.total} ocorrências rastreáveis`; issueBox.append(total);
  for (const group of issues.groups) { const line = document.createElement("p"); line.textContent = `${group.issue_code}: ${group.count} (${group.status})`; issueBox.append(line); }
}

async function exportReport() {
  const params = new URLSearchParams({date_from: byId("report-date-from").value, date_to: byId("report-date-to").value});
  const response = await api(`/reports/appointments.csv?${params}`);
  const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a");
  link.href = url; link.download = "atendimentos.csv"; link.click(); URL.revokeObjectURL(url);
}

async function downloadDocument(item) {
  try {
    const response = await api(`/documents/${item.id}/download`);
    const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a");
    link.href = url; link.download = item.original_name; link.click(); URL.revokeObjectURL(url);
  } catch (error) { showToast(error.message, "error"); }
}

byId("login-form").addEventListener("submit", async (event) => {
  event.preventDefault(); byId("login-error").textContent = "";
  try {
    const result = await api("/auth/login", {method: "POST", body: JSON.stringify({username: byId("login-user").value, password: byId("login-password").value})});
    if (result.must_reset_password) { state.user = result.user; showView("password-view"); return; }
    await establishSession(await api("/auth/me"));
  } catch (error) { byId("login-error").textContent = error.message; }
});

byId("password-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/auth/password", {method: "POST", body: JSON.stringify({current_password: byId("current-password").value, new_password: byId("new-password").value})});
    showToast("Senha alterada. Entre novamente."); showView("login-view");
  } catch (error) { showToast(error.message, "error"); }
});

byId("logout-button").addEventListener("click", async () => { try { await api("/auth/logout", {method: "POST"}); } finally { state.user = null; showView("login-view"); } });
byId("patient-form").addEventListener("submit", async (event) => { event.preventDefault(); try { const patient = await api("/patients", {method: "POST", body: JSON.stringify({name: byId("patient-name").value, cpf: byId("patient-cpf").value || null, phone: byId("patient-phone").value || null})}); byId("patient-result").textContent = `Paciente ID ${patient.id}`; byId("appointment-patient").value = patient.id; showToast("Paciente cadastrado"); } catch (error) { showToast(error.message, "error"); } });
byId("appointment-form").addEventListener("submit", async (event) => { event.preventDefault(); try { const item = await api("/appointments", {method: "POST", body: JSON.stringify({patient_id: Number(byId("appointment-patient").value), exam_date: byId("appointment-date").value, renach: byId("appointment-renach").value || null})}); showToast(`Atendimento ${item.id} criado`); await loadAppointments(); } catch (error) { showToast(error.message, "error"); } });
byId("payment-form").addEventListener("submit", async (event) => { event.preventDefault(); const sources = [["pix","payment-pix"],["dinheiro","payment-cash"],["cartao","payment-card"],["cheque","payment-check"]]; const items = sources.map(([method,id]) => ({method, amount: Number(byId(id).value || 0).toFixed(2)})).filter((item) => Number(item.amount) > 0); const total = items.reduce((sum,item) => sum + Number(item.amount),0).toFixed(2); try { await api("/finance/payments", {method: "POST", body: JSON.stringify({appointment_id: Number(byId("payment-appointment").value), total_amount: total, items})}); showToast("Pagamento registrado"); await loadFinance(); } catch (error) { showToast(error.message, "error"); } });
byId("document-form").addEventListener("submit", async (event) => { event.preventDefault(); const form = new FormData(); form.set("document_type", byId("document-type").value); form.set("file", byId("document-file").files[0]); try { await api(`/documents/appointments/${Number(byId("document-appointment").value)}`, {method: "POST", body: form}); showToast("Documento enviado"); await loadDocuments(Number(byId("document-appointment").value)); } catch (error) { showToast(error.message, "error"); } });
byId("clinical-worklist-refresh").addEventListener("click", () => loadClinicalWorklist().catch((error) => showToast(error.message, "error")));
byId("delivery-queue-refresh").addEventListener("click", () => loadDeliveryQueue().catch((error) => showToast(error.message, "error")));
byId("user-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const payload = userPayload();
    if (state.editingUser) {
      await api(`/admin/users/${state.editingUser.id}`, {method: "PUT", body: JSON.stringify({...payload, active: byId("edit-active").checked, expected_version: state.editingUser.row_version})});
      showToast("Usuário atualizado; sessões antigas foram revogadas se o acesso mudou");
    } else {
      const result = await api("/admin/users", {method: "POST", body: JSON.stringify({username: byId("new-username").value, ...payload})});
      byId("admin-result").textContent = `Senha temporária de ${result.user.username}: ${result.temporary_password}`;
      showToast("Usuário criado; copie a senha temporária agora");
    }
    clearUserForm(); await loadUsers();
  } catch (error) { showToast(error.message, "error"); }
});
byId("report-form").addEventListener("submit", (event) => { event.preventDefault(); runReport().catch((error) => showToast(error.message, "error")); });
byId("export-report").addEventListener("click", () => exportReport().catch((error) => showToast(error.message, "error")));
byId("finance-period").addEventListener("change", () => { setFinancePeriodDates(); state.financeReportPage = 1; });
byId("finance-report-form").addEventListener("submit", (event) => { event.preventDefault(); state.financeReportPage = 1; loadFinanceReport().catch((error) => showToast(error.message, "error")); });
byId("finance-export").addEventListener("click", () => exportFinanceReport().catch((error) => showToast(error.message, "error")));
byId("finance-prev").addEventListener("click", () => { if (state.financeReportPage > 1) { state.financeReportPage -= 1; loadFinanceReport().catch((error) => showToast(error.message, "error")); } });
byId("finance-next").addEventListener("click", () => { if (state.financeReportPage < state.financeReportPages) { state.financeReportPage += 1; loadFinanceReport().catch((error) => showToast(error.message, "error")); } });
byId("patient-finance-search-form").addEventListener("submit", (event) => { event.preventDefault(); searchPatientFinance().catch((error) => showToast(error.message, "error")); });
byId("patient-finance-export").addEventListener("click", () => exportPatientFinance().catch((error) => showToast(error.message, "error")));
byId("user-search-form").addEventListener("submit", (event) => { event.preventDefault(); loadUsers().catch((error) => showToast(error.message, "error")); });
byId("user-search-clear").addEventListener("click", () => { byId("user-search").value = ""; loadUsers().catch((error) => showToast(error.message, "error")); });
byId("user-cancel-edit").addEventListener("click", clearUserForm);
byId("new-role").addEventListener("change", syncProfessionalRequirement);
byId("search-button").addEventListener("click", () => loadAppointments().catch((error) => showToast(error.message,"error")));
byId("refresh-button").addEventListener("click", () => refreshAll().catch((error) => showToast(error.message,"error")));
document.querySelectorAll(".tabs button").forEach((button) => button.addEventListener("click", () => { document.querySelectorAll(".tabs button").forEach((item) => item.classList.remove("active")); button.classList.add("active"); document.querySelectorAll(".panel").forEach((panel) => { panel.hidden = panel.id !== button.dataset.panel; }); if (button.dataset.panel === "panel-users") loadUsers().catch((error) => showToast(error.message, "error")); if (button.dataset.panel === "panel-reports") runReport().catch((error) => showToast(error.message, "error")); if (button.dataset.panel === "panel-finance" && hasRole("gerente")) Promise.all([loadFinanceUsers(), loadFinanceReport()]).catch((error) => showToast(error.message, "error")); if (button.dataset.panel === "panel-documents") Promise.all([loadClinicalWorklist(), loadDeliveryQueue()]).catch((error) => showToast(error.message, "error")); }));

byId("appointment-date").value = new Date().toISOString().slice(0, 10);
byId("report-date-from").value = new Date().toISOString().slice(0, 10);
byId("report-date-to").value = new Date().toISOString().slice(0, 10);
setFinancePeriodDates();
syncProfessionalRequirement();
byId("today-label").textContent = new Intl.DateTimeFormat("pt-BR", {dateStyle: "full"}).format(new Date());
api("/auth/me").then((user) => user.must_reset_password ? showView("password-view") : establishSession(user)).catch(() => showView("login-view"));
