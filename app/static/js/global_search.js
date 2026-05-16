// Búsqueda global / paleta de comandos (Cmd/Ctrl+K)
// Índice estático de acciones, listados y conceptos.
(function () {
    "use strict";

    const SEARCH_INDEX = [
        // ---- Apuntar (acciones rápidas) ----
        { label: "Apuntar gasto", section: "Apuntar", icon: "bi-arrow-down-circle-fill",
          keywords: ["gasto", "factura", "gasoil", "compra", "expense", "pagar", "comprar"],
          url: "/expenses/new" },
        { label: "Apuntar ingreso", section: "Apuntar", icon: "bi-arrow-up-circle-fill",
          keywords: ["ingreso", "venta", "income", "cobrar", "vender", "factura"],
          url: "/incomes/new" },
        { label: "Apuntar cosecha", section: "Apuntar", icon: "bi-basket-fill",
          keywords: ["cosecha", "recolecta", "trufa", "kilos", "harvest"],
          url: "/harvests/new" },
        { label: "Apuntar lluvia", section: "Apuntar", icon: "bi-cloud-rain-fill",
          keywords: ["lluvia", "mm", "agua", "precipitacion", "precipitación"],
          url: "/lluvia/nuevo" },
        { label: "Apuntar labor", section: "Apuntar", icon: "bi-tools",
          keywords: ["labor", "trabajo", "tarea", "evento", "poda", "tratamiento"],
          url: "/plot-events/new" },
        { label: "Apuntar riego", section: "Apuntar", icon: "bi-droplet-fill",
          keywords: ["riego", "regar", "irrigation", "agua"],
          url: "/irrigation/new" },

        // ---- Crear ----
        { label: "Crear parcela", section: "Crear", icon: "bi-grid-fill",
          keywords: ["parcela", "bancal", "nueva", "alta", "plot"],
          url: "/plots/new" },
        { label: "Crear pozo", section: "Crear", icon: "bi-droplet-half",
          keywords: ["pozo", "wells", "agua", "alta"],
          url: "/wells/new" },

        // ---- Listados ----
        { label: "Mis parcelas", section: "Listados", icon: "bi-grid",
          keywords: ["parcelas", "bancales", "listado", "explotacion"],
          url: "/plots/" },
        { label: "Mis gastos", section: "Listados", icon: "bi-receipt",
          keywords: ["gastos", "listado", "facturas"],
          url: "/expenses/" },
        { label: "Mis ingresos", section: "Listados", icon: "bi-cash-coin",
          keywords: ["ingresos", "ventas", "listado"],
          url: "/incomes/" },
        { label: "Mis cosechas", section: "Listados", icon: "bi-basket",
          keywords: ["cosechas", "trufa", "produccion", "producción"],
          url: "/harvests/" },
        { label: "Mis pozos", section: "Listados", icon: "bi-droplet",
          keywords: ["pozos", "wells"],
          url: "/wells/" },
        { label: "Lluvia (historial)", section: "Listados", icon: "bi-cloud-drizzle",
          keywords: ["lluvia", "historial", "precipitaciones"],
          url: "/lluvia/" },
        { label: "Calendario de lluvia", section: "Listados", icon: "bi-calendar3",
          keywords: ["calendario", "lluvia", "calendar"],
          url: "/lluvia/calendario" },
        { label: "Brulé", section: "Listados", icon: "bi-circle-square",
          keywords: ["brule", "brulé", "quemado", "ruedo"],
          url: "/brule/" },
        { label: "Gastos recurrentes", section: "Listados", icon: "bi-arrow-repeat",
          keywords: ["recurrentes", "suscripcion", "cuotas", "mensual"],
          url: "/recurring-expenses/" },

        // ---- Análisis ----
        { label: "Rentabilidad", section: "Análisis", icon: "bi-graph-up-arrow",
          keywords: ["rentabilidad", "beneficio", "perdida", "pérdida", "roi", "profitability"],
          url: "/reports/profitability" },
        { label: "KPIs por parcela", section: "Análisis", icon: "bi-bar-chart-line",
          keywords: ["kpi", "kpis", "analitica", "analítica", "parcela"],
          url: "/kpis/" },
        { label: "Análisis por parcela", section: "Análisis", icon: "bi-pie-chart",
          keywords: ["analisis", "análisis", "parcela", "plot-analytics"],
          url: "/plot-analytics/" },
        { label: "Calidad de producción", section: "Análisis", icon: "bi-award",
          keywords: ["calidad", "quality", "categoria", "categoría"],
          url: "/quality-analytics/" },
        { label: "Tiempo / meteorología", section: "Análisis", icon: "bi-cloud-sun",
          keywords: ["tiempo", "meteo", "meteorologia", "meteorología", "aemet"],
          url: "/tiempo/" },
        { label: "Mapa de explotación", section: "Análisis", icon: "bi-map",
          keywords: ["mapa", "map", "satelite", "satélite"],
          url: "/maps/" },

        // ---- Datos ----
        { label: "Importar datos (CSV)", section: "Datos", icon: "bi-cloud-upload",
          keywords: ["importar", "import", "csv", "excel", "subir"],
          url: "/import/" },
        { label: "Exportar datos", section: "Datos", icon: "bi-cloud-download",
          keywords: ["exportar", "export", "descargar", "backup"],
          url: "/export/" },

        // ---- Cuenta ----
        { label: "Mi perfil", section: "Cuenta", icon: "bi-person",
          keywords: ["perfil", "cuenta", "profile", "datos"],
          url: "/profile/" },
        { label: "Mi suscripción", section: "Cuenta", icon: "bi-credit-card",
          keywords: ["plan", "suscripcion", "suscripción", "facturacion", "billing", "premium"],
          url: "/billing/" },
        { label: "Avisos", section: "Cuenta", icon: "bi-bell",
          keywords: ["avisos", "notificaciones", "notifications"],
          url: "/notifications/" },

        // ---- Ayuda ----
        { label: "Centro de ayuda", section: "Ayuda", icon: "bi-life-preserver",
          keywords: ["ayuda", "help", "soporte", "faq"],
          url: "/ayuda/" },
        { label: "Glosario de términos", section: "Ayuda", icon: "bi-book",
          keywords: ["glosario", "terminos", "términos", "brule", "campaña", "definiciones"],
          url: "/ayuda/glosario" },
    ];

    function normalize(s) {
        return (s || "")
            .toString()
            .toLowerCase()
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "");
    }

    function score(item, q) {
        if (!q) return 0;
        const label = normalize(item.label);
        const section = normalize(item.section);
        const kws = (item.keywords || []).map(normalize);
        if (label === q) return 1000;
        if (label.startsWith(q)) return 500;
        if (label.includes(q)) return 250;
        if (kws.some(k => k === q)) return 200;
        if (kws.some(k => k.startsWith(q))) return 150;
        if (kws.some(k => k.includes(q))) return 100;
        if (section.includes(q)) return 50;
        // Fuzzy: todos los caracteres en orden
        let i = 0;
        for (const c of q) {
            i = label.indexOf(c, i);
            if (i === -1) return 0;
            i++;
        }
        return 10;
    }

    function buildModal() {
        if (document.getElementById("tf-global-search-modal")) return;
        const html = `
        <div class="modal fade" id="tf-global-search-modal" tabindex="-1" aria-hidden="true" aria-labelledby="tf-search-title">
          <div class="modal-dialog modal-dialog-centered modal-lg">
            <div class="modal-content shadow">
              <div class="modal-header py-2 px-3">
                <i class="bi bi-search me-2 text-muted"></i>
                <input type="search" id="tf-global-search-input"
                       class="form-control form-control-lg border-0"
                       placeholder="Buscar acciones, listados, ayuda…"
                       aria-label="Buscar" autocomplete="off">
                <button type="button" class="btn-close ms-2" data-bs-dismiss="modal" aria-label="Cerrar"></button>
              </div>
              <div class="modal-body p-2" id="tf-global-search-results" role="listbox"></div>
              <div class="modal-footer py-1 px-3 small text-muted d-flex justify-content-between">
                <span><kbd>↑</kbd> <kbd>↓</kbd> moverse · <kbd>Enter</kbd> ir · <kbd>Esc</kbd> cerrar</span>
                <span id="tf-search-title">Búsqueda global</span>
              </div>
            </div>
          </div>
        </div>`;
        const wrap = document.createElement("div");
        wrap.innerHTML = html;
        document.body.appendChild(wrap.firstElementChild);
    }

    function renderResults(results, container, activeIdx) {
        if (!results.length) {
            container.innerHTML = `<div class="tf-search-empty">
                <i class="bi bi-emoji-neutral d-block mb-2 fs-4"></i>
                Nada encontrado. Prueba con otra palabra.
            </div>`;
            return;
        }
        let lastSection = null;
        const parts = [];
        results.forEach((r, idx) => {
            if (r.item.section !== lastSection) {
                lastSection = r.item.section;
                parts.push(`<div class="text-uppercase fw-semibold text-muted small px-2 pt-2 pb-1">${r.item.section}</div>`);
            }
            const active = idx === activeIdx ? " is-active" : "";
            parts.push(`<a href="${r.item.url}" class="tf-search-result${active}" data-idx="${idx}" role="option">
                <i class="bi ${r.item.icon}"></i>
                <div class="flex-grow-1">
                    <div>${r.item.label}</div>
                </div>
                <i class="bi bi-arrow-return-left text-muted small"></i>
            </a>`);
        });
        container.innerHTML = parts.join("");
    }

    function topResults(q) {
        const nq = normalize(q.trim());
        if (!nq) {
            // sin query: muestra "Apuntar" + "Crear"
            return SEARCH_INDEX
                .filter(i => i.section === "Apuntar" || i.section === "Crear")
                .map(item => ({ item, s: 1 }));
        }
        return SEARCH_INDEX
            .map(item => ({ item, s: score(item, nq) }))
            .filter(r => r.s > 0)
            .sort((a, b) => b.s - a.s)
            .slice(0, 12);
    }

    let state = { results: [], active: 0 };

    function openModal() {
        buildModal();
        const modalEl = document.getElementById("tf-global-search-modal");
        const input = document.getElementById("tf-global-search-input");
        const container = document.getElementById("tf-global-search-results");
        state.results = topResults("");
        state.active = 0;
        renderResults(state.results, container, state.active);

        const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
        modal.show();
        modalEl.addEventListener("shown.bs.modal", () => input.focus(), { once: true });

        input.oninput = () => {
            state.results = topResults(input.value);
            state.active = 0;
            renderResults(state.results, container, state.active);
        };

        modalEl.onkeydown = (e) => {
            if (e.key === "ArrowDown") {
                e.preventDefault();
                state.active = Math.min(state.active + 1, state.results.length - 1);
                renderResults(state.results, container, state.active);
            } else if (e.key === "ArrowUp") {
                e.preventDefault();
                state.active = Math.max(state.active - 1, 0);
                renderResults(state.results, container, state.active);
            } else if (e.key === "Enter") {
                e.preventDefault();
                const target = state.results[state.active];
                if (target) window.location.href = target.item.url;
            }
        };

        container.onclick = (e) => {
            const a = e.target.closest(".tf-search-result");
            if (!a) return;
            // dejamos navegar al href; nada que hacer
        };
    }

    document.addEventListener("keydown", (e) => {
        const isCmdK = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k";
        const isSlash = e.key === "/" && !e.target.matches("input, textarea, select, [contenteditable]");
        if (isCmdK || isSlash) {
            e.preventDefault();
            openModal();
        }
    });

    document.addEventListener("click", (e) => {
        const trigger = e.target.closest("[data-tf-global-search]");
        if (trigger) {
            e.preventDefault();
            openModal();
        }
    });
})();
