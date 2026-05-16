/**
 * Autoguardado genérico de formularios (Trufiq · Fase 2).
 *
 * Uso:
 *     <form data-autosave-key="parcela_draft">...</form>
 *
 * - Guarda en localStorage los valores de inputs/selects/textareas con `name`
 *   cada vez que cambian (debounced 400ms).
 * - Restaura al cargar si el formulario está vacío (sin valores iniciales del
 *   servidor), evitando pisar datos de edición.
 * - Limpia el borrador automáticamente al enviar el formulario con éxito.
 * - Caduca a las 24h para no acumular datos viejos.
 *
 * Muestra el estado en cualquier elemento con `id="tf-autosave-status"`.
 */
(function () {
    "use strict";

    var TTL_MS = 24 * 60 * 60 * 1000; // 24h
    var STORAGE_PREFIX = "tf_autosave:";

    function storageKey(form) {
        var key = form.getAttribute("data-autosave-key");
        return key ? STORAGE_PREFIX + key + ":" + window.location.pathname : null;
    }

    function debounce(fn, wait) {
        var t;
        return function () {
            var args = arguments;
            clearTimeout(t);
            t = setTimeout(function () { fn.apply(null, args); }, wait);
        };
    }

    function setStatus(text) {
        var el = document.getElementById("tf-autosave-status");
        if (el) el.textContent = text;
    }

    function serializeForm(form) {
        var data = {};
        form.querySelectorAll("input[name], select[name], textarea[name]").forEach(function (el) {
            // Saltar password, file, hidden CSRF tipo tokens, y _method
            if (el.type === "password" || el.type === "file") return;
            if (el.name === "_method") return;
            // Saltar campos marcados explícitamente para no autosalvar
            if (el.hasAttribute("data-autosave-skip")) return;
            // Saltar readonly: suelen ser valores derivados (p. ej. porcentaje)
            if (el.readOnly) return;
            if (el.type === "checkbox" || el.type === "radio") {
                if (el.checked) data[el.name] = el.value;
            } else if (el.tagName === "SELECT") {
                // Para selects, guardamos cualquier valor no vacío. Las opciones
                // pueden cargarse de forma asíncrona (p. ej. municipios tras
                // elegir provincia); en restore usamos un MutationObserver.
                if (el.value !== "") data[el.name] = el.value;
            } else if (el.value !== "" && el.value !== el.defaultValue) {
                // Solo guardar lo que el usuario haya cambiado respecto al
                // valor por defecto renderizado por el servidor.
                data[el.name] = el.value;
            }
        });
        return data;
    }

    function setSelectValue(sel, value) {
        // Intenta seleccionar la opción con ese value. Si todavía no existe
        // (opciones cargadas async), observa el select hasta que aparezca.
        for (var i = 0; i < sel.options.length; i++) {
            if (sel.options[i].value === value) {
                sel.value = value;
                sel.dispatchEvent(new Event("change", { bubbles: true }));
                return;
            }
        }
        var observer = new MutationObserver(function () {
            for (var i = 0; i < sel.options.length; i++) {
                if (sel.options[i].value === value) {
                    sel.value = value;
                    sel.dispatchEvent(new Event("change", { bubbles: true }));
                    observer.disconnect();
                    return;
                }
            }
        });
        observer.observe(sel, { childList: true });
        // Auto-desconectar tras 10s para no quedar colgado
        setTimeout(function () { observer.disconnect(); }, 10000);
    }

    function applyData(form, data) {
        // Aplicar primero inputs/textareas e ir dejando los selects para el
        // final: así un select que dispara la carga de otro (provincia →
        // municipios) tiene tiempo de poblar opciones antes de buscar el
        // valor del dependiente.
        var selectEntries = [];
        Object.keys(data).forEach(function (name) {
            var els = form.querySelectorAll('[name="' + CSS.escape(name) + '"]');
            els.forEach(function (el) {
                if (el.tagName === "SELECT") {
                    selectEntries.push({ el: el, value: data[name] });
                } else if (el.type === "checkbox" || el.type === "radio") {
                    el.checked = (el.value === data[name]);
                    el.dispatchEvent(new Event("change", { bubbles: true }));
                } else {
                    el.value = data[name];
                    el.dispatchEvent(new Event("change", { bubbles: true }));
                }
            });
        });
        selectEntries.forEach(function (entry) {
            setSelectValue(entry.el, entry.value);
        });
    }

    function isFormPristine(form) {
        // Considera "limpio" un form donde ningún input rellenable ha sido
        // modificado respecto al valor por defecto renderizado por el HTML.
        // Esto evita que valores como `num_plants=0` o `percentage=0,00`
        // (defaults del servidor) impidan restaurar un borrador.
        var anyEdited = false;
        form.querySelectorAll("input[name], textarea[name]").forEach(function (el) {
            if (el.type === "hidden" || el.type === "password") return;
            if (el.readOnly) return;
            if (el.name === "recinto") return;
            if ((el.value || "") !== (el.defaultValue || "")) {
                anyEdited = true;
            }
        });
        return !anyEdited;
    }

    function formatAge(ms) {
        var minutes = Math.floor(ms / 60000);
        if (minutes < 1) return "hace menos de 1 min";
        if (minutes < 60) return "hace " + minutes + " min";
        var hours = Math.floor(minutes / 60);
        if (hours < 24) return "hace " + hours + " h";
        var days = Math.floor(hours / 24);
        return "hace " + days + " d";
    }

    function showRestoreBanner(form, payload, key) {
        // Evitar duplicar banner si ya existe
        if (form.querySelector(".tf-autosave-banner")) return;
        var banner = document.createElement("div");
        banner.className = "alert alert-warning d-flex flex-wrap align-items-center justify-content-between gap-2 tf-autosave-banner";
        banner.setAttribute("role", "alert");

        var msg = document.createElement("div");
        msg.innerHTML = '<i class="bi bi-clock-history me-2"></i>' +
            "<strong>Tienes datos sin guardar</strong> de " + formatAge(Date.now() - payload.savedAt) + ".";
        banner.appendChild(msg);

        var actions = document.createElement("div");
        actions.className = "d-flex gap-2";

        var btnRestore = document.createElement("button");
        btnRestore.type = "button";
        btnRestore.className = "btn btn-sm btn-warning";
        btnRestore.innerHTML = '<i class="bi bi-arrow-counterclockwise me-1"></i>Restaurar';
        btnRestore.addEventListener("click", function () {
            applyData(form, payload.data || {});
            setStatus("Borrador restaurado");
            banner.remove();
        });

        var btnDiscard = document.createElement("button");
        btnDiscard.type = "button";
        btnDiscard.className = "btn btn-sm btn-outline-secondary";
        btnDiscard.innerHTML = '<i class="bi bi-trash me-1"></i>Descartar';
        btnDiscard.addEventListener("click", function () {
            try { localStorage.removeItem(key); } catch (e) {}
            setStatus("");
            banner.remove();
        });

        actions.appendChild(btnRestore);
        actions.appendChild(btnDiscard);
        banner.appendChild(actions);

        form.insertBefore(banner, form.firstChild);
    }

    function loadDraft(form) {
        var key = storageKey(form);
        if (!key) return;
        var raw;
        try { raw = localStorage.getItem(key); } catch (e) { return; }
        if (!raw) return;
        var payload;
        try { payload = JSON.parse(raw); } catch (e) { return; }
        if (!payload || !payload.savedAt) return;
        if (Date.now() - payload.savedAt > TTL_MS) {
            try { localStorage.removeItem(key); } catch (e) {}
            return;
        }
        if (!isFormPristine(form)) return;
        if (!payload.data || Object.keys(payload.data).length === 0) return;
        showRestoreBanner(form, payload, key);
    }

    function saveDraft(form) {
        var key = storageKey(form);
        if (!key) return;
        var data = serializeForm(form);
        if (Object.keys(data).length === 0) {
            try { localStorage.removeItem(key); } catch (e) {}
            setStatus("");
            return;
        }
        try {
            localStorage.setItem(key, JSON.stringify({ savedAt: Date.now(), data: data }));
            setStatus("Borrador guardado");
        } catch (e) {
            // Cuota llena u otro error: silencioso
        }
    }

    function clearDraft(form) {
        var key = storageKey(form);
        if (!key) return;
        try { localStorage.removeItem(key); } catch (e) {}
    }

    function init() {
        document.querySelectorAll("form[data-autosave-key]").forEach(function (form) {
            loadDraft(form);

            var save = debounce(function () { saveDraft(form); }, 400);
            form.addEventListener("input", save);
            form.addEventListener("change", save);

            form.addEventListener("submit", function () {
                // Si el envío falla y la página recarga con errores, el
                // borrador sigue ahí. Lo limpiamos en submit; el navegador
                // restaurará valores nativos en caso de error de validación.
                clearDraft(form);
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
