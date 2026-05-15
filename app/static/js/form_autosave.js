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
            // Saltar selects: dependen a menudo de datos cargados de forma
            // asíncrona (provincia/municipio) y restaurarlos antes de tiempo
            // puede dejar el valor en blanco. Que el usuario los re-seleccione.
            if (el.tagName === "SELECT") return;
            if (el.type === "checkbox" || el.type === "radio") {
                if (el.checked) data[el.name] = el.value;
            } else if (el.value !== "") {
                data[el.name] = el.value;
            }
        });
        return data;
    }

    function applyData(form, data) {
        Object.keys(data).forEach(function (name) {
            var els = form.querySelectorAll('[name="' + CSS.escape(name) + '"]');
            els.forEach(function (el) {
                if (el.type === "checkbox" || el.type === "radio") {
                    el.checked = (el.value === data[name]);
                } else {
                    el.value = data[name];
                }
                // Disparar change para que listeners (geo dropdowns, etc.) reaccionen
                el.dispatchEvent(new Event("change", { bubbles: true }));
            });
        });
    }

    function isFormPristine(form) {
        // Considera "limpio" un form donde solo hay valores que el HTML traía
        // por defecto. Como aproximación: si NINGÚN input rellenable tiene
        // valor introducido por el usuario (más allá de defaults razonables),
        // restauramos. Para el caso de creación de parcela esto se cumple.
        var anyFilled = false;
        form.querySelectorAll("input[name], textarea[name]").forEach(function (el) {
            if (el.type === "hidden" || el.type === "password") return;
            if ((el.value || "").trim() && el.name !== "recinto") {
                anyFilled = true;
            }
        });
        return !anyFilled;
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
        applyData(form, payload.data || {});
        setStatus("Borrador restaurado");
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
