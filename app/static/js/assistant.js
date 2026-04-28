(function () {
    // ── Resize handle ──────────────────────────────────────────────────────────
    (function () {
        var STORAGE_KEY = 'tf-assistant-width';
        var MIN_W = 300;
        var MAX_W = Math.round(window.screen.width * 0.9);
        var panel = document.getElementById('assistantPanel');
        var handle = document.getElementById('assistantResizeHandle');
        if (!panel || !handle) return;

        // Restore saved width
        var saved = parseInt(localStorage.getItem(STORAGE_KEY), 10);
        if (saved && saved >= MIN_W && saved <= MAX_W) {
            panel.style.width = saved + 'px';
        }

        var startX, startW;

        handle.addEventListener('mousedown', function (e) {
            e.preventDefault();
            startX = e.clientX;
            startW = panel.offsetWidth;
            handle.classList.add('tf-resizing');
            document.body.style.cursor = 'ew-resize';
            document.body.style.userSelect = 'none';

            function onMouseMove(e) {
                var delta = startX - e.clientX; // dragging left = wider
                var newW = Math.min(MAX_W, Math.max(MIN_W, startW + delta));
                panel.style.width = newW + 'px';
            }

            function onMouseUp() {
                handle.classList.remove('tf-resizing');
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
                localStorage.setItem(STORAGE_KEY, panel.offsetWidth);
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
            }

            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });
    }());

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
                if (window.marked) {
                    // Protect LaTeX blocks from marked's escape handling (\[ → [)
                    var maths = [];
                    var safe = text
                        .replace(/\\\[[\s\S]*?\\\]/g, function (m) {
                            maths.push(m);
                            return '\x00MATH' + (maths.length - 1) + '\x00';
                        })
                        .replace(/\\\([\s\S]*?\\\)/g, function (m) {
                            maths.push(m);
                            return '\x00MATH' + (maths.length - 1) + '\x00';
                        });
                    var html = marked.parse(safe);
                    maths.forEach(function (m, i) {
                        html = html.split('\x00MATH' + i + '\x00').join(m);
                    });
                    content.innerHTML = html;
                } else {
                    content.textContent = text;
                }
                if (window.renderMathInElement) {
                    renderMathInElement(content, {
                        delimiters: [
                            { left: '\\[', right: '\\]', display: true },
                            { left: '\\(', right: '\\)', display: false }
                        ],
                        throwOnError: false
                    });
                }
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
        var micBtn = document.getElementById('assistantMicBtn');

        if (!form || !input || !messages || !sendBtn || !cancelBtn) {
            return;
        }

        var history = [];
        var controller = null;
        var mediaRecorder = null;
        var audioChunks = [];

        function setLoading(loading) {
            sendBtn.disabled = loading;
            cancelBtn.disabled = !loading;
            input.disabled = loading;
            if (micBtn) {
                micBtn.disabled = loading;
            }
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

        function micSetRecording(recording) {
            if (!micBtn) return;
            if (recording) {
                micBtn.classList.remove('btn-outline-secondary');
                micBtn.classList.add('btn-danger');
                micBtn.innerHTML = '<i class="bi bi-stop-circle-fill me-1"></i>Detener';
            } else {
                micBtn.classList.remove('btn-danger');
                micBtn.classList.add('btn-outline-secondary');
                micBtn.innerHTML = '<i class="bi bi-mic-fill me-1"></i>Voz';
            }
        }

        function transcribeBlob(blob) {
            micBtn.disabled = true;
            var ext = blob.type.includes('webm') ? 'webm' : blob.type.includes('ogg') ? 'ogg' : 'wav';
            var formData = new FormData();
            formData.append('file', blob, 'audio.' + ext);
            fetch('/api/assistant/transcribe', {
                method: 'POST',
                body: formData
            })
                .then(function (response) {
                    if (!response.ok) {
                        return response.json().then(function (json) {
                            throw new Error(json.detail || 'Error al transcribir');
                        });
                    }
                    return response.json();
                })
                .then(function (data) {
                    if (data.text) {
                        input.value = data.text;
                        form.dispatchEvent(new Event('submit'));
                    }
                })
                .catch(function (err) {
                    pushMessage('system', 'No se pudo transcribir el audio: ' + err.message);
                })
                .finally(function () {
                    micBtn.disabled = false;
                });
        }

        if (micBtn) {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || typeof MediaRecorder === 'undefined') {
                micBtn.disabled = true;
                micBtn.title = 'Tu navegador no soporta grabación de audio';
            } else {
                micBtn.addEventListener('click', function () {
                    if (mediaRecorder && mediaRecorder.state === 'recording') {
                        mediaRecorder.stop();
                        micSetRecording(false);
                    } else {
                        audioChunks = [];
                        navigator.mediaDevices.getUserMedia({ audio: true })
                            .then(function (stream) {
                                var mimeType = '';
                                if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
                                    mimeType = 'audio/webm;codecs=opus';
                                } else if (MediaRecorder.isTypeSupported('audio/webm')) {
                                    mimeType = 'audio/webm';
                                } else if (MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')) {
                                    mimeType = 'audio/ogg;codecs=opus';
                                }
                                var options = mimeType ? { mimeType: mimeType } : {};
                                mediaRecorder = new MediaRecorder(stream, options);

                                mediaRecorder.ondataavailable = function (event) {
                                    if (event.data.size > 0) {
                                        audioChunks.push(event.data);
                                    }
                                };

                                mediaRecorder.onstop = function () {
                                    stream.getTracks().forEach(function (track) { track.stop(); });
                                    var blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
                                    transcribeBlob(blob);
                                };

                                mediaRecorder.start();
                                micSetRecording(true);
                            })
                            .catch(function () {
                                pushMessage('system', 'No se pudo acceder al micrófono. Comprueba los permisos.');
                            });
                    }
                });
            }
        }

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
