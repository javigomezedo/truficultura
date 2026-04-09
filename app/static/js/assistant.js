(function () {
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

        function formatTraceability(traceability, intent) {
            if (!traceability) {
                return '';
            }
            var sources = Array.isArray(traceability.sources) ? traceability.sources : [];
            var scope = traceability.data_scope || 'sin especificar';
            var mode = traceability.retrieval_mode || 'static';
            var head = 'Contexto usado: ' + intent + ' (' + scope + ', mode=' + mode + ')';
            if (!sources.length) {
                return head;
            }
            return head + '\nFuentes: ' + sources.join(', ');
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

            var assistantNode = pushMessage('assistant', '');
            var assistantText = '';

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
                            var traceMsg = formatTraceability(evt.traceability, evt.intent);
                            if (traceMsg) {
                                pushMessage('system', traceMsg);
                            }
                        }
                        if (evt.type === 'token') {
                            assistantText += evt.delta || '';
                            assistantNode.textContent = assistantText;
                            messages.scrollTop = messages.scrollHeight;
                        }
                        if (evt.type === 'error') {
                            assistantNode.textContent = evt.message || 'No se pudo completar la respuesta.';
                        }
                    });
                })
                .then(function () {
                    history.push({ role: 'user', content: question });
                    history.push({ role: 'assistant', content: assistantText || assistantNode.textContent });
                    history = history.slice(-10);
                })
                .catch(function (error) {
                    if (error.name !== 'AbortError') {
                        assistantNode.textContent = 'No se pudo completar la respuesta: ' + error.message;
                    }
                })
                .finally(function () {
                    controller = null;
                    setLoading(false);
                    input.focus();
                });
        });
    }

    document.addEventListener('DOMContentLoaded', setupAssistant);
})();
