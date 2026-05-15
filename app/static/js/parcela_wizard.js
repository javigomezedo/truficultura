/**
 * Wizard de creación de parcela (Trufiq · Fase 2).
 *
 * Toma el formulario con `.tf-wizard` y muestra un paso a la vez.
 * Los pasos se identifican por `.tf-wizard-step[data-step]`.
 * Los botones esperados:
 *   #tf-wizard-prev, #tf-wizard-next, #tf-wizard-submit
 *   #tf-wizard-progress (barra), #tf-wizard-status (texto)
 *   .tf-step-pill[data-step-pill]  (las píldoras del stepper)
 *
 * - Valida con la API nativa HTML5 los campos requeridos del paso actual
 *   antes de avanzar.
 * - El botón submit solo aparece en el último paso.
 * - Accesible: enfoca el primer campo del paso al cambiar, ARIA-live updates.
 */
(function () {
    "use strict";

    var form = document.getElementById("tf-plot-form");
    if (!form || !form.classList.contains("tf-wizard")) return;

    var steps = Array.prototype.slice.call(
        form.querySelectorAll(".tf-wizard-step")
    );
    if (steps.length === 0) return;

    var prevBtn   = document.getElementById("tf-wizard-prev");
    var nextBtn   = document.getElementById("tf-wizard-next");
    var submitBtn = document.getElementById("tf-wizard-submit");
    var progress  = document.getElementById("tf-wizard-progress");
    var statusEl  = document.getElementById("tf-wizard-status");
    var pills     = document.querySelectorAll(".tf-step-pill[data-step-pill]");

    var current = 1;
    var total = steps.length;

    function showStep(n, userInitiated) {
        current = Math.max(1, Math.min(total, n));
        steps.forEach(function (s) {
            var sn = parseInt(s.getAttribute("data-step"), 10);
            s.classList.toggle("is-active", sn === current);
        });
        pills.forEach(function (p) {
            var pn = parseInt(p.getAttribute("data-step-pill"), 10);
            p.classList.toggle("is-active", pn === current);
            p.classList.toggle("is-done", pn < current);
        });
        if (prevBtn) prevBtn.disabled = (current === 1);
        if (nextBtn) nextBtn.classList.toggle("d-none", current === total);
        if (submitBtn) submitBtn.classList.toggle("d-none", current !== total);
        if (progress) {
            progress.style.width = Math.round((current / total) * 100) + "%";
        }
        if (statusEl) {
            statusEl.textContent = "Paso " + current + " de " + total;
        }
        // Foco en el primer campo visible y editable del paso actual,
        // solo cuando el cambio ha sido iniciado por el usuario.
        if (userInitiated) {
            var active = form.querySelector('.tf-wizard-step.is-active');
            if (active) {
                var firstField = active.querySelector(
                    'input:not([type=hidden]):not([readonly]), select, textarea'
                );
                if (firstField) {
                    try { firstField.focus({ preventScroll: false }); } catch (e) {}
                }
                active.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        }
    }

    function validateStep(n) {
        var step = form.querySelector('.tf-wizard-step[data-step="' + n + '"]');
        if (!step) return true;
        var invalidEl = null;
        var fields = step.querySelectorAll('input, select, textarea');
        for (var i = 0; i < fields.length; i++) {
            var f = fields[i];
            if (f.disabled || f.type === 'hidden') continue;
            if (!f.checkValidity()) {
                invalidEl = f;
                break;
            }
        }
        if (invalidEl) {
            invalidEl.reportValidity();
            return false;
        }
        return true;
    }

    if (nextBtn) {
        nextBtn.addEventListener("click", function () {
            if (!validateStep(current)) return;
            showStep(current + 1, true);
        });
    }
    if (prevBtn) {
        prevBtn.addEventListener("click", function () {
            showStep(current - 1, true);
        });
    }

    // Permitir saltar a un paso ya visitado pulsando su píldora
    pills.forEach(function (p) {
        p.style.cursor = 'pointer';
        p.addEventListener('click', function () {
            var target = parseInt(p.getAttribute('data-step-pill'), 10);
            if (target < current) {
                showStep(target, true);
            } else if (target > current) {
                // Solo permitir avance si todos los pasos previos validan
                for (var s = current; s < target; s++) {
                    if (!validateStep(s)) { showStep(s, true); return; }
                }
                showStep(target, true);
            }
        });
    });

    // Validar todos los pasos al hacer submit (por si el usuario llega aquí
    // sin pasar por validate al pulsar Enter)
    form.addEventListener('submit', function (ev) {
        for (var s = 1; s <= total; s++) {
            if (!validateStep(s)) {
                ev.preventDefault();
                showStep(s, true);
                return;
            }
        }
    });

    // Si el usuario pulsa Enter en un campo, no debe enviar el form mientras
    // no esté en el último paso: mejor avanzar.
    form.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter' && ev.target.tagName !== 'TEXTAREA') {
            if (current < total) {
                ev.preventDefault();
                if (validateStep(current)) showStep(current + 1, true);
            }
        }
    });

    // Estado inicial
    showStep(1, false);
})();
