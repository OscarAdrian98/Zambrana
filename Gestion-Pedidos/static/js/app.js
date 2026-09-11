/**
 * app.js - Gestion Pedidos PrestaShop <-> Ambar
 */

const LAST_PEDIDO_SCROLL_KEY = 'gp:lastPedidoScroll';
const NEW_ORDERS_LAST_ID_KEY = 'gp:newOrdersLastId';
const NEW_ORDERS_ENABLED_KEY = 'gp:newOrdersEnabled';
const NEW_ORDERS_SOUND_KEY = 'gp:newOrdersSound';
const NEW_ORDERS_AUTOREFRESH_KEY = 'gp:newOrdersAutoRefresh';
const NEW_ORDERS_POLL_MS = 30000;

window.gestionPedidosAccionEnCurso = false;
window.gestionPedidosPollingActivo = false;
window.gestionPedidosNewOrdersTimer = null;
window.gestionPedidosOriginalTitle = document.title;
window.gestionPedidosEmailModal = null;

function setHoy() {
    const hoy = new Date().toISOString().slice(0, 10);
    document.getElementById('fecha_desde').value = hoy;
    document.getElementById('fecha_hasta').value = hoy;
}

function addIdPedido() {
    const div = document.getElementById('divIDAdd');
    const inp = document.createElement('input');
    inp.type = 'text';
    inp.name = 'ids_multiples[]';
    inp.placeholder = 'ID';
    inp.className = 'form-control form-control-sm mt-1';
    inp.style.width = '80px';
    div.appendChild(inp);
}

function toggleOrden() {
    const hidden = document.getElementById('direccion_orden');
    const icon = document.getElementById('iconOrden');
    const btn = document.getElementById('btnOrden');
    if (hidden.value === 'DESC') {
        hidden.value = 'ASC';
        icon.className = 'bi bi-sort-up';
        btn.title = 'Ascendente';
    } else {
        hidden.value = 'DESC';
        icon.className = 'bi bi-sort-down';
        btn.title = 'Descendente';
    }
}

function resetFiltros() {
    ['fecha_desde', 'fecha_hasta', 'id_pedido', 'ultimos_n'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
    document.getElementById('divIDAdd').innerHTML = '';
    document.getElementById('hora_fin_dia').value = '23:00';
    const sel = document.getElementById('modos_pago');
    if (sel) Array.from(sel.options).forEach(o => { o.selected = false; });
    const estados = document.getElementById('estados_pedido');
    if (estados) Array.from(estados.options).forEach(o => { o.selected = false; });
    const estadosInternos = document.getElementById('estados_internos');
    if (estadosInternos) Array.from(estadosInternos.options).forEach(o => { o.selected = false; });
    document.getElementById('radioFactura').checked = true;
    document.getElementById('contentTabla').innerHTML = '';
}

function mostrarToast(html) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const div = document.createElement('div');
    div.innerHTML = html;
    const toastEl = div.firstElementChild;
    if (!toastEl) return;
    container.appendChild(toastEl);
    const bsToast = new bootstrap.Toast(toastEl, { delay: 6000 });
    bsToast.show();
    toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
}

function refrescarTablaResultados() {
    const form = document.getElementById('frmFiltros');
    if (!form) return;
    if (window.htmx) {
        window.htmx.trigger(form, 'submit');
    } else {
        form.dispatchEvent(new Event('submit', { bubbles: true }));
    }
}

function guardarPedidoScroll(idPedido) {
    if (!idPedido) return;
    sessionStorage.setItem(LAST_PEDIDO_SCROLL_KEY, String(idPedido));
}

function restaurarPedidoScroll(scope = document) {
    const idPedido = sessionStorage.getItem(LAST_PEDIDO_SCROLL_KEY);
    if (!idPedido) return;
    const row = scope.querySelector(`#pedido-${idPedido}`);
    if (!row) return;
    row.scrollIntoView({ behavior: 'smooth', block: 'center' });
    row.classList.add('fila-highlight-restaurada');
    window.setTimeout(() => row.classList.remove('fila-highlight-restaurada'), 1800);
    sessionStorage.removeItem(LAST_PEDIDO_SCROLL_KEY);
}

async function htmxPost(url, formData, options = {}) {
    const { refreshOnSuccess = false } = options;
    const spinner = document.getElementById('spinner-global');
    window.gestionPedidosAccionEnCurso = true;
    spinner?.classList.remove('d-none');
    console.info('[HTMX-POST] inicio', { url, refreshOnSuccess });
    try {
        const resp = await fetch(url, { method: 'POST', body: formData });
        const html = await resp.text();
        console.info('[HTMX-POST] respuesta', { url, status: resp.status, ok: resp.ok, bodyPreview: html.slice(0, 180) });
        mostrarToast(html);

        const okResponse = html.includes('text-bg-success');
        if (refreshOnSuccess && okResponse) {
            refrescarTablaResultados();
        }
    } catch (err) {
        mostrarToast(`<div class="toast show text-bg-danger border-0"><div class="toast-body"><i class="bi bi-exclamation-triangle-fill me-2"></i>Error de red: ${err}</div></div>`);
    } finally {
        window.gestionPedidosAccionEnCurso = false;
        spinner?.classList.add('d-none');
    }
}

function getStoredBool(key, defaultValue) {
    const raw = localStorage.getItem(key);
    if (raw === null) return defaultValue;
    return raw === '1';
}

function setStoredBool(key, value) {
    localStorage.setItem(key, value ? '1' : '0');
}

function getCurrentLastPedidoId() {
    const rows = Array.from(document.querySelectorAll('tr[id^="pedido-"]'));
    let maxId = 0;
    rows.forEach(row => {
        const idText = String(row.id || '').replace('pedido-', '').trim();
        const idNum = parseInt(idText, 10);
        if (!Number.isNaN(idNum) && idNum > maxId) maxId = idNum;
    });
    return maxId;
}

function getLastPedidoIdForPolling() {
    const stored = parseInt(localStorage.getItem(NEW_ORDERS_LAST_ID_KEY) || '0', 10);
    if (!Number.isNaN(stored) && stored > 0) return stored;
    const banner = document.getElementById('new-orders-banner');
    const initial = parseInt(banner?.dataset?.initialLastId || '0', 10);
    if (!Number.isNaN(initial) && initial > 0) return initial;
    return getCurrentLastPedidoId();
}

function setLastPedidoIdForPolling(value) {
    const safeValue = Math.max(0, parseInt(value || '0', 10) || 0);
    localStorage.setItem(NEW_ORDERS_LAST_ID_KEY, String(safeValue));
}

function isNewOrdersEnabled() {
    const chk = document.getElementById('chk_pedidos_nuevos');
    return !!chk?.checked;
}

function isNewOrdersSoundEnabled() {
    const chk = document.getElementById('chk_pedidos_nuevos_sonido');
    return !!chk?.checked;
}

function isNewOrdersAutoRefreshEnabled() {
    const chk = document.getElementById('chk_pedidos_nuevos_autorefresh');
    return !!chk?.checked;
}

function updateNewOrdersTitle(count) {
    if (count > 0) {
        document.title = `(${count}) Nuevo pedido - ${window.gestionPedidosOriginalTitle}`;
        return;
    }
    document.title = window.gestionPedidosOriginalTitle;
}

function playNewOrdersSound() {
    if (!isNewOrdersSoundEnabled()) return;
    try {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) return;
        const ctx = new AudioContextClass();
        const startAt = ctx.currentTime + 0.02;
        const beepDuration = 0.18;
        const beepGap = 0.14;
        const beepVolume = 0.75;

        const playBeep = (offsetSeconds, frequency) => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            const beepStart = startAt + offsetSeconds;
            const beepEnd = beepStart + beepDuration;

            osc.type = 'sine';
            osc.frequency.setValueAtTime(frequency, beepStart);

            gain.gain.setValueAtTime(0.0001, beepStart);
            gain.gain.exponentialRampToValueAtTime(beepVolume, beepStart + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.0001, beepEnd);

            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start(beepStart);
            osc.stop(beepEnd);
        };

        playBeep(0, 720);
        playBeep(beepDuration + beepGap, 660);

        window.setTimeout(() => {
            if (typeof ctx.close === 'function' && ctx.state !== 'closed') {
                ctx.close().catch(() => {});
            }
        }, 1000);
    } catch (err) {
        console.debug('Audio de pedidos nuevos no disponible en este momento');
    }
}

function renderNewOrdersBanner(pedidos) {
    const banner = document.getElementById('new-orders-banner');
    const text = document.getElementById('new-orders-banner-text');
    if (!banner || !text || !pedidos.length) return;
    const first = pedidos[0];
    const totalFmt = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' })
        .format(Number(first.total || 0));
    const extra = pedidos.length > 1 ? ` (+${pedidos.length - 1} más)` : '';
    text.textContent = `Nuevo pedido #${first.id_order} - ${first.cliente || 'Cliente'} - ${totalFmt} - ${first.payment || '-'}${extra}`;
    banner.classList.remove('d-none');
    banner.classList.add('d-flex');
}

function hideNewOrdersBanner() {
    const banner = document.getElementById('new-orders-banner');
    if (!banner) return;
    banner.classList.add('d-none');
    banner.classList.remove('d-flex');
}

function maybeRefreshTableForNewOrders() {
    if (!isNewOrdersAutoRefreshEnabled()) return;
    if (window.gestionPedidosAccionEnCurso) return;
    refrescarTablaResultados();
}

async function pollNewOrders() {
    if (!isNewOrdersEnabled()) return;
    if (window.gestionPedidosAccionEnCurso) return;
    if (window.gestionPedidosPollingActivo) return;

    const lastId = getLastPedidoIdForPolling();
    window.gestionPedidosPollingActivo = true;
    try {
        const resp = await fetch(`/pedidos/nuevos?last_id=${encodeURIComponent(lastId)}`, {
            method: 'GET',
            headers: { 'Accept': 'application/json' },
        });
        const data = await resp.json();
        if (!resp.ok || !data?.ok) return;

        const maxId = Number(data.max_id || 0);
        if (maxId > 0) setLastPedidoIdForPolling(maxId);

        if (data.hay_nuevos && Array.isArray(data.pedidos) && data.pedidos.length > 0) {
            renderNewOrdersBanner(data.pedidos);
            updateNewOrdersTitle(Number(data.count || data.pedidos.length || 1));
            playNewOrdersSound();
            mostrarToast(
                `<div class="toast show text-bg-info border-0"><div class="toast-body"><i class="bi bi-bell-fill me-2"></i>Se han detectado ${data.count} pedido(s) nuevo(s).</div></div>`
            );
            maybeRefreshTableForNewOrders();
        }
    } catch (err) {
        console.warn('Error consultando pedidos nuevos', err);
    } finally {
        window.gestionPedidosPollingActivo = false;
    }
}

function restartNewOrdersPolling() {
    if (window.gestionPedidosNewOrdersTimer) {
        window.clearInterval(window.gestionPedidosNewOrdersTimer);
        window.gestionPedidosNewOrdersTimer = null;
    }
    if (!isNewOrdersEnabled()) {
        hideNewOrdersBanner();
        updateNewOrdersTitle(0);
        return;
    }
    window.gestionPedidosNewOrdersTimer = window.setInterval(pollNewOrders, NEW_ORDERS_POLL_MS);
}

function initNewOrdersControls() {
    const chkEnabled = document.getElementById('chk_pedidos_nuevos');
    const chkSound = document.getElementById('chk_pedidos_nuevos_sonido');
    const chkAutoRefresh = document.getElementById('chk_pedidos_nuevos_autorefresh');
    const btnRefresh = document.getElementById('btn-refresh-new-orders');
    if (!chkEnabled || !chkSound || !chkAutoRefresh) return;

    chkEnabled.checked = getStoredBool(NEW_ORDERS_ENABLED_KEY, true);
    chkSound.checked = getStoredBool(NEW_ORDERS_SOUND_KEY, true);
    chkAutoRefresh.checked = getStoredBool(NEW_ORDERS_AUTOREFRESH_KEY, false);

    setLastPedidoIdForPolling(getLastPedidoIdForPolling());

    chkEnabled.addEventListener('change', () => {
        setStoredBool(NEW_ORDERS_ENABLED_KEY, chkEnabled.checked);
        restartNewOrdersPolling();
    });
    chkSound.addEventListener('change', () => setStoredBool(NEW_ORDERS_SOUND_KEY, chkSound.checked));
    chkAutoRefresh.addEventListener('change', () => setStoredBool(NEW_ORDERS_AUTOREFRESH_KEY, chkAutoRefresh.checked));
    btnRefresh?.addEventListener('click', () => {
        hideNewOrdersBanner();
        updateNewOrdersTitle(0);
        if (!window.gestionPedidosAccionEnCurso) {
            refrescarTablaResultados();
        }
    });

    restartNewOrdersPolling();
}

function resolverCliente(radioName, defaultCliente) {
    const radios = document.getElementsByName(radioName);
    for (const r of radios) {
        if (r.checked) return r.value;
    }
    return defaultCliente;
}

function accionCrearCliente(d, options = {}) {
    if (d.id_pedido) guardarPedidoScroll(d.id_pedido);
    const fd = new FormData();
    Object.entries(d).forEach(([k, v]) => fd.append(k, v));
    htmxPost('/clientes/crear', fd, options);
}

function accionPrevisualizarCliente(idPedido, usarDireccion) {
    const fd = new FormData();
    fd.append('id_pedido', idPedido);
    fd.append('usar_direccion', usarDireccion || 'Factura');
    htmxPost('/clientes/previsualizar', fd);
}

function accionRegistrarAnticipo(idPedido, usarDireccion) {
    guardarPedidoScroll(idPedido);
    const fd = new FormData();
    fd.append('id_pedido', idPedido);
    fd.append('usar_direccion', usarDireccion || 'Factura');
    fd.append('hora_fin_dia', document.getElementById('hora_fin_dia')?.value || '23:00');
    htmxPost('/anticipos/crear', fd, { refreshOnSuccess: true });
}

function obtenerClienteManualSeleccionado(idPedido) {
    const checked = document.querySelector(`input[name="cliente_ambar_manual_${idPedido}"]:checked`);
    return checked ? String(checked.value || '').trim() : '';
}

function setEmailPedidoStatus(message, type = 'muted') {
    const statusEl = document.getElementById('emailPedidoStatus');
    if (!statusEl) return;
    statusEl.className = `small text-${type}`;
    statusEl.textContent = message || '';
}

function abrirModalEmailPedido(idPedido, email, cliente, referencia) {
    const modalEl = document.getElementById('modalEmailPedido');
    if (!modalEl || !window.bootstrap) return;

    if (!window.gestionPedidosEmailModal) {
        window.gestionPedidosEmailModal = new bootstrap.Modal(modalEl);
    }

    const pedidoNum = parseInt(idPedido || '0', 10) || 0;
    document.getElementById('emailPedidoIdPedido').value = String(pedidoNum);
    document.getElementById('emailPedidoPedidoInfo').value = referencia
        ? `#${pedidoNum} - ${referencia}`
        : `#${pedidoNum}`;
    document.getElementById('emailPedidoClienteInfo').value = (cliente || '').trim();
    document.getElementById('emailPedidoTo').value = (email || '').trim();
    document.getElementById('emailPedidoSubject').value = `Pedido MX demo #${pedidoNum}`;
    document.getElementById('emailPedidoBody').value = '';
    setEmailPedidoStatus('', 'muted');

    const btnEnviar = document.getElementById('btnEnviarEmailPedido');
    if (btnEnviar) {
        btnEnviar.disabled = false;
        btnEnviar.querySelector('.btn-label').textContent = 'Enviar correo';
    }

    window.gestionPedidosEmailModal.show();
}

async function enviarEmailPedido() {
    const idPedido = parseInt(document.getElementById('emailPedidoIdPedido')?.value || '0', 10);
    const toEmail = (document.getElementById('emailPedidoTo')?.value || '').trim();
    const subject = (document.getElementById('emailPedidoSubject')?.value || '').trim();
    const body = (document.getElementById('emailPedidoBody')?.value || '').trim();
    const btnEnviar = document.getElementById('btnEnviarEmailPedido');
    const label = btnEnviar?.querySelector('.btn-label');

    if (!idPedido) {
        setEmailPedidoStatus('Pedido invalido.', 'danger');
        return;
    }
    if (!toEmail) {
        setEmailPedidoStatus('El pedido no tiene email destino.', 'danger');
        return;
    }
    if (!subject) {
        setEmailPedidoStatus('El asunto no puede estar vacio.', 'danger');
        return;
    }
    if (!body) {
        setEmailPedidoStatus('El cuerpo del correo no puede estar vacio.', 'danger');
        return;
    }

    btnEnviar.disabled = true;
    if (label) label.textContent = 'Enviando...';
    setEmailPedidoStatus('Enviando correo...', 'info');
    window.gestionPedidosAccionEnCurso = true;

    try {
        const resp = await fetch(`/pedidos/${idPedido}/email/enviar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify({
                to_email: toEmail,
                subject,
                body,
            }),
        });
        const data = await resp.json();
        if (!resp.ok || !data?.ok) {
            setEmailPedidoStatus(data?.message || 'No se pudo enviar el correo.', 'danger');
            return;
        }
        setEmailPedidoStatus(data.message || 'Correo enviado correctamente.', 'success');
        window.setTimeout(() => {
            window.gestionPedidosEmailModal?.hide();
        }, 1200);
    } catch (err) {
        setEmailPedidoStatus('Error de red al enviar correo.', 'danger');
    } finally {
        btnEnviar.disabled = false;
        if (label) label.textContent = 'Enviar correo';
        window.gestionPedidosAccionEnCurso = false;
    }
}

function formatImporteEur(value) {
    return new Intl.NumberFormat('es-ES', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(Number(value || 0));
}

function updateAnticipoManualUI(idPedido) {
    const dataEl = document.getElementById(`anticipo-manual-data-${idPedido}`);
    const stateEl = document.getElementById(`anticipo-selected-state-${idPedido}`);
    const actionWrap = document.getElementById(`anticipo-action-wrap-${idPedido}`);
    if (!dataEl || !stateEl) return;

    let data = null;
    try {
        data = JSON.parse(dataEl.textContent || '{}');
    } catch (err) {
        return;
    }

    const clienteManual = obtenerClienteManualSeleccionado(idPedido);
    const equivalentes = data?.equivalentes_por_cliente || {};
    const recientes = data?.recientes_por_cliente || {};
    const equivalente = clienteManual ? equivalentes[clienteManual] : null;
    const reciente = clienteManual ? recientes[clienteManual] : null;

    if (!clienteManual) {
        stateEl.className = 'text-warning aviso-negocio small mt-1';
        stateEl.innerHTML = 'Selecciona primero el cliente Ambar correcto.';
        actionWrap?.classList.add('d-none');
        actionWrap?.classList.remove('d-flex');
        return;
    }

    if (equivalente) {
        stateEl.className = 'text-warning aviso-negocio small mt-1';
        stateEl.innerHTML = `Ya existe anticipo equivalente para el cliente seleccionado (#${equivalente.codigo})<div class="text-muted text-secondary-line mt-1">${equivalente.fecha} · ${formatImporteEur(equivalente.importe_entregado)} EUR · ${equivalente.forma_pago} · Bco ${equivalente.banco}</div>`;
        actionWrap?.classList.add('d-none');
        actionWrap?.classList.remove('d-flex');
        return;
    }

    if (reciente) {
        stateEl.className = 'text-muted text-secondary-line small mt-1';
        stateEl.innerHTML = `Último anticipo del cliente seleccionado: #${reciente.codigo} · ${formatImporteEur(reciente.importe_entregado)} EUR · ${reciente.fecha}`;
    } else {
        stateEl.className = 'text-muted text-secondary-line small mt-1';
        stateEl.innerHTML = 'El cliente seleccionado no tiene anticipo equivalente para este pedido.';
    }

    if (data?.puede_mostrar_accion && !data?.read_only) {
        actionWrap?.classList.remove('d-none');
        actionWrap?.classList.add('d-flex');
    }
}

function initAnticipoManualUI(scope = document) {
    scope.querySelectorAll('script[id^="anticipo-manual-data-"]').forEach(el => {
        const idPedido = String(el.id).replace('anticipo-manual-data-', '').trim();
        if (idPedido) updateAnticipoManualUI(idPedido);
    });
}

function accionActivarCliente(idCliente, idPedido = '') {
    if (!confirm(`¿Reactivar el cliente ${idCliente} en Ambar?`)) return;
    if (idPedido) guardarPedidoScroll(idPedido);
    htmxPost(`/clientes/${idCliente}/activar`, new FormData(), { refreshOnSuccess: true });
}

function accionAnticipo(d) {
    const idCliente = resolverCliente(d.radio, d.idcliente);
    const horaFin = document.getElementById('hora_fin_dia')?.value || '23:00';
    const fd = new FormData();
    fd.append('id_pedido_ps', d.idpedido);
    fd.append('id_cliente_ambar', idCliente);
    fd.append('fecha_pedido', d.fecha);
    fd.append('total_pedido', d.total);
    fd.append('forma_pago_ambar', d.formapago);
    fd.append('cod_banco', d.banco);
    fd.append('cc_cliente', d.cc);
    fd.append('hora_fin_dia', horaFin);
    htmxPost('/anticipos/crear', fd);
}

function accionCrearPedido(d) {
    const idCliente = resolverCliente(d.radio, d.idcliente);
    if (!idCliente) {
        alert('Seleccione un cliente Ambar');
        return;
    }
    const fd = new FormData();
    fd.append('id_pedido_ps', d.idpedido);
    fd.append('id_cliente_ambar', idCliente);
    htmxPost('/ambar/pedidos/crear', fd);
}

function accionCrearPedidoReal(idPedido, usarDireccion, clienteManual = '') {
    guardarPedidoScroll(idPedido);
    const fd = new FormData();
    fd.append('id_pedido', idPedido);
    fd.append('usar_direccion', usarDireccion || 'Factura');
    if (clienteManual) fd.append('cliente_ambar_manual', clienteManual);
    htmxPost('/ambar/pedidos/crear', fd, { refreshOnSuccess: true });
}

function accionCambiarEstadoPrestashop(btn) {
    const idPedido = btn.dataset.idpedido;
    const row = btn.closest('tr');
    const select = row ? row.querySelector('[data-role="estado-select"]') : null;
    const idOrderState = select ? select.value : '';
    console.info('[EstadoPS] click detectado');
    console.info(`[EstadoPS] pedido detectado=${idPedido || '-'}`);
    console.info(`[EstadoPS] estado detectado=${idOrderState || '-'}`);
    if (!idPedido || !idOrderState) {
        console.error('[EstadoPS] datos invalidos', { idPedido, idOrderState });
        mostrarToast('<div class="toast show text-bg-warning border-0"><div class="toast-body"><i class="bi bi-exclamation-circle me-2"></i>Seleccione un estado valido.</div></div>');
        return;
    }
    const fd = new FormData();
    fd.append('id_pedido', idPedido);
    fd.append('id_order_state', idOrderState);
    fd.append('send_email', '0');
    guardarPedidoScroll(idPedido);
    console.info('[EstadoPS] enviando POST /prestashop/estado/cambiar');
    htmxPost('/prestashop/estado/cambiar', fd, { refreshOnSuccess: true });
}

function accionCambiarEstadoInterno(select) {
    const idPedido = select?.dataset?.idpedido || '';
    const idInternalState = select?.value || '';
    if (!idPedido || !idInternalState) {
        mostrarToast('<div class="toast show text-bg-warning border-0"><div class="toast-body"><i class="bi bi-exclamation-circle me-2"></i>Seleccione un Estado Interno valido.</div></div>');
        return;
    }
    const fd = new FormData();
    fd.append('id_internal_state', idInternalState);
    guardarPedidoScroll(idPedido);
    htmxPost(`/pedidos/${idPedido}/estado-interno`, fd, { refreshOnSuccess: true });
}

function copiarMensaje(texto) {
    navigator.clipboard.writeText(texto).then(() => {
        mostrarToast('<div class="toast show text-bg-info border-0"><div class="toast-body"><i class="bi bi-clipboard-check me-2"></i>Mensaje copiado al portapapeles</div></div>');
    });
}

function accionToggleStockPanel(idPedido, btn) {
    const row = document.getElementById(`stock-row-${idPedido}`);
    const panel = document.getElementById(`stock-panel-${idPedido}`);
    if (!row || !panel || !window.htmx) return;

    const visible = !row.classList.contains('d-none');
    if (visible) {
        row.classList.add('d-none');
        if (btn) btn.textContent = 'Ver stock';
        return;
    }

    row.classList.remove('d-none');
    if (btn) btn.textContent = 'Ocultar stock';

    if (!panel.dataset.loaded) {
        window.htmx.ajax('GET', `/pedidos/${idPedido}/comprobacion-stock`, {
            target: `#stock-panel-${idPedido}`,
            swap: 'innerHTML',
        });
        panel.dataset.loaded = '1';
    }
}

function accionToggleValidacionClientePanel(idPedido, btn) {
    const row = document.getElementById(`validacion-cliente-row-${idPedido}`);
    const panel = document.getElementById(`validacion-cliente-panel-${idPedido}`);
    if (!row || !panel || !window.htmx) return;

    const visible = !row.classList.contains('d-none');
    if (visible) {
        row.classList.add('d-none');
        if (btn) {
            btn.textContent = 'Ver diferencias';
            btn.classList.remove('is-open');
        }
        return;
    }

    row.classList.remove('d-none');
    if (btn) {
        btn.textContent = 'Ocultar diferencias';
        btn.classList.add('is-open');
    }

    if (!panel.dataset.loaded) {
        window.htmx.ajax('GET', `/pedidos/${idPedido}/validacion-cliente`, {
            target: `#validacion-cliente-panel-${idPedido}`,
            swap: 'innerHTML',
        });
        panel.dataset.loaded = '1';
    }
}

async function copiarClienteAmbar(btn) {
    const numero = (btn?.dataset?.cliente || '').trim();
    if (!numero) return;
    try {
        if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(numero);
        } else {
            const ta = document.createElement('textarea');
            ta.value = numero;
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            ta.remove();
        }
        const icon = btn.querySelector('i');
        if (icon) icon.className = 'bi bi-check2';
        btn.classList.add('is-copied');
        btn.title = 'Copiado';
        window.setTimeout(() => {
            if (icon) icon.className = 'bi bi-clipboard';
            btn.classList.remove('is-copied');
            btn.title = 'Copiar cliente Ambar';
        }, 1200);
    } catch (err) {
        mostrarToast('<div class="toast show text-bg-danger border-0"><div class="toast-body"><i class="bi bi-exclamation-triangle-fill me-2"></i>No se pudo copiar el cliente.</div></div>');
    }
}

function onEstadoPSClickDelegated(e) {
    const btnEstado = e.target.closest('[data-action="cambiar-estado-ps"]');
    if (btnEstado) {
        e.preventDefault();
        e.stopPropagation();
        accionCambiarEstadoPrestashop(btnEstado);
        return;
    }
}

// Delegacion en captura para evitar submit implicito incluso tras re-render HTMX.
document.addEventListener('click', onEstadoPSClickDelegated, true);

document.addEventListener('click', function (e) {
    const btnEstado = e.target.closest('[data-action="cambiar-estado-ps"]');
    if (btnEstado) return;

    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    e.preventDefault();

    const action = btn.dataset.action;
    const d = btn.dataset;

    switch (action) {
        case 'previsualizar-cliente':
            accionPrevisualizarCliente(d.idpedido, d.usardireccion);
            break;

        case 'crear-cliente-real':
            accionCrearCliente(
                {
                    id_pedido: d.idpedido,
                    usar_direccion: d.usardireccion || 'Factura',
                },
                { refreshOnSuccess: true },
            );
            break;

        case 'crear-cliente':
            accionCrearCliente({
                dni: d.dni,
                nombre: d.nombre,
                direccion: d.direccion,
                ciudad: d.ciudad,
                provincia: d.provincia,
                pais: d.pais,
                cod_pais: d.codpais,
                postal: d.postal,
                telefono: d.telefono,
                movil: d.movil,
                email: d.email,
                tiene_iva: d.tieneiva,
            });
            break;

        case 'registrar-anticipo-real':
            if (d.requiereClienteManual === '1') {
                const clienteManual = obtenerClienteManualSeleccionado(d.idpedido);
                if (!clienteManual) {
                    mostrarToast('<div class="toast show text-bg-warning border-0"><div class="toast-body"><i class="bi bi-person-check me-2"></i>Selecciona primero un cliente Ambar para este pedido.</div></div>');
                    return;
                }
                const fd = new FormData();
                guardarPedidoScroll(d.idpedido);
                fd.append('id_pedido', d.idpedido);
                fd.append('usar_direccion', d.usardireccion || 'Factura');
                fd.append('hora_fin_dia', document.getElementById('hora_fin_dia')?.value || '23:00');
                fd.append('cliente_ambar_manual', clienteManual);
                htmxPost('/anticipos/crear', fd, { refreshOnSuccess: true });
                return;
            }
            accionRegistrarAnticipo(d.idpedido, d.usardireccion);
            break;

        case 'activar-cliente':
            accionActivarCliente(d.idcliente, d.idpedido || '');
            break;

        case 'anticipo':
            accionAnticipo(d);
            break;

        case 'crear-pedido':
            accionCrearPedido(d);
            break;

        case 'crear-pedido-real':
            if (d.requiereClienteManual === '1') {
                const clienteManual = obtenerClienteManualSeleccionado(d.idpedido);
                if (!clienteManual) {
                    mostrarToast('<div class="toast show text-bg-warning border-0"><div class="toast-body"><i class="bi bi-person-check me-2"></i>Selecciona primero un cliente Ambar para este pedido.</div></div>');
                    return;
                }
                accionCrearPedidoReal(d.idpedido, d.usardireccion, clienteManual);
                return;
            }
            accionCrearPedidoReal(d.idpedido, d.usardireccion);
            break;
        case 'copiar-cliente-ambar':
            copiarClienteAmbar(btn);
            break;
        case 'toggle-stock-panel':
            accionToggleStockPanel(d.idpedido, btn);
            break;
        case 'toggle-validacion-cliente-panel':
            accionToggleValidacionClientePanel(d.idpedido, btn);
            break;
        case 'abrir-modal-email-pedido':
            abrirModalEmailPedido(d.idpedido, d.email, d.cliente, d.referencia);
            break;

    }
});

document.addEventListener('change', function (e) {
    const estadoInterno = e.target.closest('[data-role="internal-state-select"]');
    if (estadoInterno) {
        accionCambiarEstadoInterno(estadoInterno);
        return;
    }

    const radio = e.target.closest('input[type="radio"][name^="cliente_ambar_manual_"]');
    if (!radio) return;
    const idPedido = String(radio.name || '').replace('cliente_ambar_manual_', '').trim();
    if (!idPedido) return;
    updateAnticipoManualUI(idPedido);
});

document.addEventListener('htmx:afterSwap', evt => {
    evt.target.querySelectorAll('.toast').forEach(el => {
        new bootstrap.Toast(el, { delay: 6000 }).show();
    });
    restaurarPedidoScroll(evt.target);
    setLastPedidoIdForPolling(Math.max(getLastPedidoIdForPolling(), getCurrentLastPedidoId()));
    hideNewOrdersBanner();
    updateNewOrdersTitle(0);
    initAnticipoManualUI(evt.target);
});

document.addEventListener('htmx:beforeRequest', () => {
    window.gestionPedidosAccionEnCurso = true;
});

document.addEventListener('htmx:afterRequest', () => {
    window.gestionPedidosAccionEnCurso = false;
});

document.addEventListener('DOMContentLoaded', () => {
    restaurarPedidoScroll(document);
    initNewOrdersControls();
    initAnticipoManualUI(document);
    document.getElementById('btnEnviarEmailPedido')?.addEventListener('click', enviarEmailPedido);
});
