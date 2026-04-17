(function () {
    var SUGGESTED_QUESTION_GROUPS = [
        {
            title: 'Rentabilidad',
            questions: [
                '¿Qué parcela tiene peor rentabilidad ajustada si repartimos los gastos generales?',
                '¿Cuál fue mi mejor campaña y por qué indicadores destaca?',
                '¿Qué categorías de gasto son las más altas y qué persona acumula más gastos?'
            ]
        },
        {
            title: 'Producción y campo',
            questions: [
                '¿Qué categorías de ingreso aportan más facturación y cuáles más kilos?',
                '¿Cuánto de mi producción registrada viene por QR frente a registro manual?',
                '¿Qué parcelas tienen vallado, pozo o labores relevantes registradas?'
            ]
        },
        {
            title: 'Problemas y oportunidades',
            questions: [
                'Dame un resumen por parcela con ingresos, gastos, rentabilidad, agua aplicada y si tiene vallado.',
                '¿Qué parcela tiene riego activo pero baja producción o rentabilidad?',
                '¿Dónde parece que estoy gastando más y obteniendo menos retorno?'
            ]
        }
    ];

    function createMessageElement(role, text) {
        var el = document.createElement('div');
        el.classList.add('tf-assistant-msg');
        if (role === 'user') {
            el.classList.add('tf-assistant-msg-user');
        } else if (role === 'assistant') {
            el.classList.add('tf-assistant-msg-assistant');
        } else {
            el.classList.add('tf-assistant-msg-system');
        }
        el.textContent = text;
        return el;
    }

    function createAssistantMessageElement() {
        var el = document.createElement('div');
        el.classList.add('tf-assistant-msg', 'tf-assistant-msg-assistant');

        var content = document.createElement('div');
        content.classList.add('tf-assistant-msg-content');
        el.appendChild(content);

        return {
            element: el,
            setText: function (text) {
                content.textContent = text;
            },
            attachTraceability: function (traceability, intent) {
                if (!traceability) {
                    return;
                }

                var existing = el.querySelector('.tf-assistant-trace');
                if (existing) {
                    existing.remove();
                }

                var details = document.createElement('details');
                details.classList.add('tf-assistant-trace');

                var summary = document.createElement('summary');
                summary.classList.add('tf-assistant-trace-summary');
                summary.innerHTML = '<i class="bi bi-info-circle"></i><span>Contexto</span>';
                details.appendChild(summary);

                var body = document.createElement('div');
                body.classList.add('tf-assistant-trace-body');

                var sources = Array.isArray(traceability.sources) ? traceability.sources : [];
                var scope = traceability.data_scope || 'sin especificar';
                var mode = traceability.retrieval_mode || 'static';
                var contextLine = document.createElement('div');
                contextLine.textContent = 'Tipo: ' + intent + ' | alcance: ' + scope + ' | modo: ' + mode;
                body.appendChild(contextLine);

                if (sources.length) {
                    var sourcesLine = document.createElement('div');
                    sourcesLine.textContent = 'Fuentes: ' + sources.join(', ');
                    body.appendChild(sourcesLine);
                }

                details.appendChild(body);
                el.appendChild(details);
            }
        };
    }

    function readSSEStream(response, onEvent) {
        if (!response.body) {
            throw new Error('No stream body available');
        }

        var reader = response.body.getReader();
        var decoder = new TextDecoder('utf-8');
        var buffer = '';

        function pump() {
            return reader.read().then(function (result) {
                if (result.done) {
                    return;
                }

                buffer += decoder.decode(result.value, { stream: true });
                var lines = buffer.split('\n');
                buffer = lines.pop() || '';

                lines.forEach(function (line) {
                    var trimmed = line.trim();
                    if (!trimmed || trimmed.indexOf('data: ') !== 0) {
                        return;
                    }
                    var payload = trimmed.slice(6);
                    try {
                        var parsed = JSON.parse(payload);
                        onEvent(parsed);
                    } catch (e) {
                        // Ignore malformed chunks.
                    }
                });

                return pump();
            });
        }

        return pump();
    }

    function setupAssistant() {
        var form = document.getElementById('assistantForm');
        var input = document.getElementById('assistantInput');
        var messages = document.getElementById('assistantMessages');
        var suggestionsList = document.getElementById('assistantSuggestionsList');
        var suggestionsDetails = document.getElementById('assistantSuggestions');
        var sendBtn = document.getElementById('assistantSendBtn');
        var cancelBtn = document.getElementById('assistantCancelBtn');

        if (!form || !input || !messages || !sendBtn || !cancelBtn) {
            return;
        }

        var history = [];
        var controller = null;

        function setLoading(loading) {
            sendBtn.disabled = loading;
            cancelBtn.disabled = !loading;
            input.disabled = loading;
        }

        function pushMessage(role, text) {
            var node = createMessageElement(role, text);
            messages.appendChild(node);
            messages.scrollTop = messages.scrollHeight;
            return node;
        }

        function renderSuggestions() {
            if (!suggestionsList) {
                return;
            }

            SUGGESTED_QUESTION_GROUPS.forEach(function (group) {
                var section = document.createElement('section');
                section.classList.add('tf-assistant-suggestion-group');

                var title = document.createElement('h6');
                title.classList.add('tf-assistant-suggestion-group-title');
                title.textContent = group.title;
                section.appendChild(title);

                var list = document.createElement('div');
                list.classList.add('tf-assistant-suggestion-group-items');

                group.questions.forEach(function (question) {
                    var button = document.createElement('button');
                    button.type = 'button';
                    button.classList.add('tf-assistant-suggestion-btn');
                    button.textContent = question;
                    button.addEventListener('click', function () {
                        input.value = question;
                        if (suggestionsDetails) {
                            suggestionsDetails.open = false;
                        }
                        messages.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                        input.focus();
                    });
                    list.appendChild(button);
                });

                section.appendChild(list);
                suggestionsList.appendChild(section);
            });
        }

        cancelBtn.addEventListener('click', function () {
            if (controller) {
                controller.abort();
                controller = null;
                setLoading(false);
                pushMessage('system', 'Respuesta cancelada por el usuario.');
            }
        });

        form.addEventListener('submit', function (event) {
            event.preventDefault();
            var question = input.value.trim();
            if (!question) {
                return;
            }

            pushMessage('user', question);
            input.value = '';

            var assistantNode = createAssistantMessageElement();
            messages.appendChild(assistantNode.element);
            messages.scrollTop = messages.scrollHeight;
            var assistantText = '';
            var pendingTraceability = null;
            var pendingIntent = null;

            controller = new AbortController();
            setLoading(true);

            fetch('/api/assistant/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                signal: controller.signal,
                body: JSON.stringify({
                    message: question,
                    history: history
                })
            })
                .then(function (response) {
                    if (!response.ok) {
                        return response.json().then(function (json) {
                            throw new Error(json.detail || 'Error de servidor');
                        });
                    }
                    return readSSEStream(response, function (evt) {
                        if (evt.type === 'ready') {
                            pendingTraceability = evt.traceability || null;
                            pendingIntent = evt.intent || null;
                            assistantNode.attachTraceability(pendingTraceability, pendingIntent);
                        }
                        if (evt.type === 'token') {
                            assistantText += evt.delta || '';
                            assistantNode.setText(assistantText);
                            messages.scrollTop = messages.scrollHeight;
                        }
                        if (evt.type === 'error') {
                            assistantNode.setText(evt.message || 'No se pudo completar la respuesta.');
                        }
                    });
                })
                .then(function () {
                    history.push({ role: 'user', content: question });
                    history.push({ role: 'assistant', content: assistantText || assistantNode.element.textContent });
                    history = history.slice(-10);
                })
                .catch(function (error) {
                    if (error.name !== 'AbortError') {
                        assistantNode.setText('No se pudo completar la respuesta: ' + error.message);
                    }
                })
                .finally(function () {
                    controller = null;
                    setLoading(false);
                    input.focus();
                });
        });

        renderSuggestions();
    }

    document.addEventListener('DOMContentLoaded', setupAssistant);
})();
