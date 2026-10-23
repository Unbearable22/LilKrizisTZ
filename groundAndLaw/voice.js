/* Local Whisper dictation: audio stays transient, only text enters chat history. */
(() => {
    let active = null;
    const supported = !!(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);
    function release(s) {
        clearTimeout(s.timer);
        s.stream?.getTracks().forEach(track => track.stop());
        s.stream = null;
    }
    function finish(s, message) {
        release(s);
        s.chunks = [];
        if (active !== s) return;
        active = null;
        document.querySelectorAll('[data-voice]').forEach(b => { b.disabled = !supported; });
        s.button.setAttribute('aria-pressed', 'false');
        s.button.title = 'Продиктовать вопрос';
        s.cancel.hidden = true;
        s.input.readOnly = false;
        s.send.disabled = s.sendDisabled;
        s.status.textContent = message;
    }
    function cancel() {
        const s = active;
        if (!s) return;
        s.cancelled = true;
        s.controller.abort();
        if (s.recorder?.state === 'recording') s.recorder.stop();
        finish(s, 'Запись отменена.');
    }
    async function upload(s) {
        release(s);
        if (s.cancelled || active !== s) return;
        s.button.disabled = true;
        s.status.textContent = 'Распознаём речь…';
        const blob = new Blob(s.chunks, {type: s.recorder.mimeType || 'audio/webm'});
        s.chunks = [];
        const timeout = setTimeout(() => s.controller.abort(), 100000);
        try {
            if (!blob.size || blob.size > 8 * 1024 * 1024) throw new Error('Запись пуста или слишком большая. Запишите вопрос короче.');
            const response = await fetch('/api/transcribe', {method: 'POST', headers: {'Content-Type': blob.type}, body: blob, signal: s.controller.signal});
            const result = await response.json();
            if (!response.ok || typeof result.text !== 'string') throw new Error(result.answer || 'Не удалось распознать речь. Попробуйте ещё раз.');
            if (s.cancelled || active !== s) return;
            const text = [s.input.value.trim(), result.text.trim()].filter(Boolean).join(' ');
            if (text.length > 8000) throw new Error('Для текста не хватает места. Сократите вопрос и повторите диктовку.');
            s.input.value = text;
            s.input.dispatchEvent(new Event('input', {bubbles: true}));
            finish(s, 'Текст готов. Проверьте адреса, даты и номера, затем отправьте вопрос.');
            s.input.focus();
        } catch (error) {
            if (!s.cancelled) finish(s, error.name === 'AbortError' ? 'Истекло время распознавания. Попробуйте короткую запись.' : error.message);
        } finally { clearTimeout(timeout); }
    }
    async function start(prefix, button, status, cancelButton) {
        if (active) {
            if (active.button === button && active.recorder?.state === 'recording') active.recorder.stop();
            return;
        }
        const input = document.getElementById(prefix + 'Input');
        const send = document.getElementById(prefix + 'SendBtn');
        const s = {button, input, send, status, cancel: cancelButton, chunks: [], controller: new AbortController(), sendDisabled: send.disabled};
        active = s;
        input.readOnly = true; send.disabled = true; cancelButton.hidden = false;
        document.querySelectorAll('[data-voice]').forEach(b => { b.disabled = true; });
        status.textContent = 'Ожидаем разрешение на микрофон…';
        try {
            s.stream = await navigator.mediaDevices.getUserMedia({audio: true});
            if (s.cancelled || active !== s) { release(s); return; }
            const mimeType = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4'].find(t => MediaRecorder.isTypeSupported(t));
            s.recorder = new MediaRecorder(s.stream, mimeType ? {mimeType} : {});
            s.recorder.ondataavailable = event => {
                if (!s.cancelled && event.data.size) {
                    s.chunks.push(event.data);
                    if (s.chunks.reduce((n, c) => n + c.size, 0) > 8 * 1024 * 1024) { cancel(); status.textContent = 'Запись слишком большая. Попробуйте короче.'; }
                }
            };
            s.recorder.onstop = () => { void upload(s); };
            s.recorder.onerror = () => { cancel(); status.textContent = 'Ошибка микрофона. Попробуйте записать ещё раз.'; };
            s.recorder.start(1000);
            button.disabled = false; button.setAttribute('aria-pressed', 'true'); button.title = 'Остановить запись';
            status.textContent = 'Идёт запись (до 2 минут). Нажмите микрофон для остановки.';
            s.timer = setTimeout(() => { if (s.recorder.state === 'recording') s.recorder.stop(); }, 120000);
        } catch (error) {
            finish(s, error.name === 'NotAllowedError' ? 'Разрешите доступ к микрофону в настройках браузера.' : 'Микрофон недоступен. Проверьте подключение и повторите.');
        }
    }
    for (const prefix of ['start', 'chat']) {
        const button = document.getElementById(prefix + 'MicBtn');
        const status = document.getElementById(prefix + 'VoiceStatus');
        const cancelButton = document.getElementById(prefix + 'VoiceCancel');
        button.disabled = !supported;
        if (!supported) status.textContent = 'Для диктовки нужен браузер с поддержкой записи микрофона и HTTPS.';
        button.addEventListener('click', () => { void start(prefix, button, status, cancelButton); });
        cancelButton.addEventListener('click', cancel);
    }
    document.addEventListener('click', e => { if (e.target.closest('#newChatBtn, .chat-item')) cancel(); }, true);
    document.addEventListener('keydown', e => { if (active && e.target === active.input && e.key === 'Enter') { e.preventDefault(); e.stopImmediatePropagation(); } }, true);
    window.addEventListener('popstate', cancel);
    window.addEventListener('pagehide', cancel);
})();
