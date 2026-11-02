// ===== ХРАНИЛИЩЕ ЧАТОВ =====
const state = {
    chats: [],
    activeChatId: null
};

let chatIdCounter = 1;
let pendingAttachments = []; // буфер вложений главного экрана

// ===== ГЕНЕРАЦИЯ ID ЧАТА =====
function generateChatId() {
    return `c_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

// ===== РОУТЕР =====
class Router {
    constructor() {
        this.routes = {
            '/': 'startScreen',
            '/chat': 'chatView'
        };
        this.currentPath = '/';
        this.transitionDuration = 300;
        this.init();
    }

    init() {
        window.addEventListener('popstate', () => {
            if (window.location.pathname === '/') {
                state.activeChatId = null;
                renderChatList();
            }
            this.navigate(window.location.pathname, false);
        });
    }

    navigate(path, pushState = true) {
        if (path === this.currentPath) return;

        const oldScreen = document.getElementById(this.routes[this.currentPath]);
        const newScreen = document.getElementById(this.routes[path]);

        if (!oldScreen || !newScreen) return;

        oldScreen.classList.add('fade-out');

        setTimeout(() => {
            oldScreen.classList.remove('active', 'fade-out');
            oldScreen.style.display = 'none';

            newScreen.style.display = 'flex';
            void newScreen.offsetHeight;
            newScreen.classList.add('active');

            if (path === '/chat') {
                document.getElementById('startScreen').classList.add('hidden');
                document.getElementById('chatView').classList.add('active');
                setTimeout(() => document.getElementById('chatInput')?.focus(), 350);
            } else {
                document.getElementById('startScreen').classList.remove('hidden');
                document.getElementById('chatView').classList.remove('active');
                setTimeout(() => document.getElementById('startInput')?.focus(), 350);
            }

            this.currentPath = path;
            if (pushState) history.pushState({}, '', path);
        }, this.transitionDuration / 2);
    }
}

const router = new Router();

// ===== РЕНДЕР СПИСКА ЧАТОВ =====
function renderChatList() {
    const container = document.getElementById('chatList');
    container.innerHTML = '';

    if (state.chats.length === 0) {
        container.innerHTML = `<div class="chat-list-empty">Нет активных чатов.<br>Начните новый диалог.</div>`;
        return;
    }

    state.chats.forEach(chat => {
        const item = document.createElement('button');
        item.className = 'chat-item';
        if (chat.id === state.activeChatId) item.classList.add('active');
        item.dataset.chatId = chat.id;

        item.innerHTML = `
            <svg class="chat-icon" viewBox="0 0 24 24">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
            </svg>
            <span class="chat-item-title"></span>
            <span class="chat-close-btn" title="Закрыть чат">
                <svg viewBox="0 0 24 24">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </span>
        `;

        item.querySelector('.chat-item-title').textContent = chat.title;

        item.addEventListener('click', (e) => {
            if (e.target.closest('.chat-close-btn')) return;
            openChat(chat.id);
        });

        item.querySelector('.chat-close-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            closeChat(chat.id);
        });

        container.appendChild(item);
    });
}

// ===== СОЗДАНИЕ ЧАТА (с сохранением в БД) =====
async function createChat(firstMessage, attachments = []) {
    // Сохраняем файлы отдельно, в чате держим только метаданные
    const savedAttachments = [];
    for (const file of attachments) {
        const meta = await ChatDB.saveFile(file);
        savedAttachments.push(meta);
    }

    const id = generateChatId();
    const title = firstMessage.length > 30
        ? firstMessage.slice(0, 30).trim() + '…'
        : (firstMessage || 'Новый чат');

    const chat = {
        id,
        title: title || 'Новый чат',
        messages: [{
            role: 'user',
            id: generateChatId(),
            text: firstMessage,
            attachments: savedAttachments
        }],
        attachments: [], // буфер текущего вложения чата
        createdAt: Date.now(),
        updatedAt: Date.now()
    };

    state.chats.unshift(chat);
    state.activeChatId = id;

    // Пишем в БД
    await ChatDB.saveChat(chat);

    return chat;
}

// ===== ОТКРЫТИЕ ЧАТА =====
function openChat(id) {
    const chat = state.chats.find(c => c.id === id);
    if (!chat) return;

    state.activeChatId = id;
    renderChatList();
    renderMessages(chat);
    refreshChatAttachments();
    router.navigate('/chat');
}

// ===== ЗАКРЫТИЕ ЧАТА =====
async function closeChat(id) {
    const index = state.chats.findIndex(c => c.id === id);
    if (index === -1) return;

    const chat = state.chats[index];
    legalClient.cancel(id);
    state.chats.splice(index, 1);

    // Удаляем чат из БД
    await ChatDB.deleteChat(id);

    // Удаляем файлы, на которые больше никто не ссылается
    await ChatDB.cleanupOrphanFiles();

    if (state.activeChatId === id) {
        state.activeChatId = null;
        renderChatList();
        router.navigate('/');
        document.getElementById('chatMessages').innerHTML = '';
        document.getElementById('chatAttachments').innerHTML = '';
    } else {
        renderChatList();
    }
}

// ===== РЕНДЕР СООБЩЕНИЙ =====
function renderMessages(chat) {
    const container = document.getElementById('chatMessages');
    container.innerHTML = '';
    if (!chat || !chat.messages.length) return;

    chat.messages.forEach(msg => {
        const el = document.createElement('div');
        el.className = `message ${msg.role === 'user' ? 'user' : ''}`;

        const avatarEl = document.createElement('div');
        avatarEl.className = 'message-avatar';
        avatarEl.textContent = msg.role === 'user' ? 'В' : 'G';

        const bubbleEl = document.createElement('div');
        bubbleEl.className = 'message-bubble';

        if (msg.text) {
            const textEl = document.createElement('div');
            textEl.textContent = msg.text;
            bubbleEl.appendChild(textEl);
        }

        if (msg.attachments && msg.attachments.length) {
            const attWrap = document.createElement('div');
            attWrap.className = 'message-attachments';
            msg.attachments.forEach(file => {
                const chip = document.createElement('div');
                chip.className = 'message-attachment';
                chip.textContent = '📎 ' + file.name;
                chip.title = 'Нажмите, чтобы скачать';
                chip.style.cursor = 'pointer';

                // Скачивание файла из IndexedDB
                chip.addEventListener('click', async () => {
                    const record = await ChatDB.getFile(file.id);
                    if (!record) {
                        alert('Файл не найден');
                        return;
                    }
                    const url = URL.createObjectURL(record.blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = record.name;
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    URL.revokeObjectURL(url);
                });

                attWrap.appendChild(chip);
            });
            bubbleEl.appendChild(attWrap);
        }

        if (msg.legal) renderLegalMessage(bubbleEl, chat, msg);

        el.appendChild(avatarEl);
        el.appendChild(bubbleEl);
        container.appendChild(el);
    });

    container.scrollTop = container.scrollHeight;
    document.getElementById('chatSendBtn').disabled = !legalReady || legalClient.busy(chat.id);
}

// ===== ДОБАВЛЕНИЕ СООБЩЕНИЯ =====
async function appendMessage(chatId, text) {
    const chat = state.chats.find(c => c.id === chatId);
    if (!chat) return;

    // Сохраняем новые файлы в БД (если есть буфер)
    const savedAttachments = [];
    if (chat.attachments && chat.attachments.length) {
        for (const file of chat.attachments) {
            // file может быть уже сохранён (если пришёл из БД) — тогда у него есть id
            if (file.id) {
                savedAttachments.push(file);
            } else {
                const meta = await ChatDB.saveFile(file);
                savedAttachments.push(meta);
            }
        }
    }

    chat.messages.push({ role: 'user', id: generateChatId(), text, attachments: savedAttachments });
    chat.attachments = [];
    chat.updatedAt = Date.now();

    await ChatDB.saveChat(chat);

    refreshChatAttachments();
    renderMessages(chat);
}

// ===== ВЛОЖЕНИЯ =====
function renderAttachments(containerId, attachments, onRemove) {
    const container = document.getElementById(containerId);
    container.innerHTML = '';

    attachments.forEach((file, index) => {
        const chip = document.createElement('div');
        chip.className = 'attachment-chip';

        const icon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        icon.setAttribute('viewBox', '0 0 24 24');
        icon.innerHTML = `
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
        `;

        const name = document.createElement('span');
        name.className = 'attachment-name';
        name.textContent = file.name;

        const remove = document.createElement('button');
        remove.className = 'attachment-remove';
        remove.type = 'button';
        remove.textContent = '×';
        remove.title = 'Убрать';
        remove.addEventListener('click', (e) => {
            e.stopPropagation();
            onRemove(index);
        });

        chip.appendChild(icon);
        chip.appendChild(name);
        chip.appendChild(remove);
        container.appendChild(chip);
    });
}

function refreshStartAttachments() {
    renderAttachments('startAttachments', pendingAttachments, (index) => {
        pendingAttachments.splice(index, 1);
        refreshStartAttachments();
    });
}

function refreshChatAttachments() {
    const chat = state.chats.find(c => c.id === state.activeChatId);
    if (!chat) return;
    renderAttachments('chatAttachments', chat.attachments || [], (index) => {
        chat.attachments.splice(index, 1);
        refreshChatAttachments();
    });
}

// ===== ИНИЦИАЛИЗАЦИЯ =====
document.addEventListener('DOMContentLoaded', async () => {
    // Стартовый экран
    document.getElementById('startScreen').style.display = 'flex';
    document.getElementById('startScreen').classList.add('active');
    document.getElementById('chatView').style.display = 'none';

    // === Загружаем чаты из БД ===
    try {
        const chatsFromDB = await ChatDB.getAllChats();
        state.chats = chatsFromDB;
        // Восстанавливаем счётчик, чтобы не было коллизий (на случай если id числовые — не наш случай, но пусть будет)
    } catch (err) {
        console.error('Ошибка загрузки чатов из IndexedDB:', err);
    } finally {
        // Прячем лоадер
        document.getElementById('appLoader').classList.add('hidden');
        setTimeout(() => {
            document.getElementById('appLoader').style.display = 'none';
        }, 350);
    }

    await connectLegal();
    renderChatList();
    setTimeout(() => document.getElementById('startInput')?.focus(), 100);

    // ===== ОТПРАВКА С ГЛАВНОГО ЭКРАНА =====
    const startInput = document.getElementById('startInput');
    const startSendBtn = document.getElementById('startSendBtn');

    async function sendFromStart() {
        if (!legalReady) return;
        const text = startInput.value.trim();
        if (!text && pendingAttachments.length === 0) return;

        startSendBtn.disabled = true;

        try {
            const chat = await createChat(text || 'Файл(ы)', pendingAttachments);

            startInput.value = '';
            startInput.style.height = 'auto';
            pendingAttachments = [];
            refreshStartAttachments();

            renderChatList();
            renderMessages(chat);
            refreshChatAttachments();
            router.navigate('/chat');
            startLegal(chat, chat.messages[0]);
        } catch (err) {
            console.error('Ошибка создания чата:', err);
            alert('Не удалось сохранить чат. Попробуйте ещё раз.');
        } finally {
            startSendBtn.disabled = false;
        }
    }

    startSendBtn.addEventListener('click', sendFromStart);
    startInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendFromStart();
        }
    });

    // ===== ОТПРАВКА В АКТИВНОМ ЧАТЕ =====
    const chatInput = document.getElementById('chatInput');
    const chatSendBtn = document.getElementById('chatSendBtn');

    async function sendFromChat() {
        if (!legalReady || legalClient.busy(state.activeChatId)) return;
        const text = chatInput.value.trim();
        const chat = state.chats.find(c => c.id === state.activeChatId);
        const hasAttachments = chat && chat.attachments && chat.attachments.length > 0;

        if ((!text && !hasAttachments) || state.activeChatId === null) return;

        chatSendBtn.disabled = true;
        try {
            const targetChat = chat;
            await appendMessage(targetChat.id, text);
            startLegal(targetChat, targetChat.messages[targetChat.messages.length-1]);
            chatInput.value = '';
            chatInput.style.height = 'auto';
        } catch (err) {
            console.error('Ошибка сохранения сообщения:', err);
            alert('Не удалось сохранить сообщение.');
        } finally {
            chatSendBtn.disabled = !legalReady || legalClient.busy(state.activeChatId);
        }
    }

    chatSendBtn.addEventListener('click', sendFromChat);
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendFromChat();
        }
    });

    // ===== КНОПКА "НОВЫЙ ЧАТ" =====
    document.getElementById('newChatBtn').addEventListener('click', () => {
        state.activeChatId = null;
        renderChatList();
        router.navigate('/');
        document.getElementById('chatMessages').innerHTML = '';
        document.getElementById('chatAttachments').innerHTML = '';
    });

    // ===== ВЛОЖЕНИЯ =====
    document.getElementById('startAttachBtn').addEventListener('click', () => {
        document.getElementById('startFileInput').click();
    });

    document.getElementById('startFileInput').addEventListener('change', (e) => {
        const files = Array.from(e.target.files);
        pendingAttachments.push(...files);
        refreshStartAttachments();
        e.target.value = '';
    });

    document.getElementById('chatAttachBtn').addEventListener('click', () => {
        document.getElementById('chatFileInput').click();
    });

    document.getElementById('chatFileInput').addEventListener('change', (e) => {
        const chat = state.chats.find(c => c.id === state.activeChatId);
        if (!chat) return;
        const files = Array.from(e.target.files);
        if (!chat.attachments) chat.attachments = [];
        chat.attachments.push(...files);
        refreshChatAttachments();
        e.target.value = '';
    });

    // ===== АВТОРОСТ TEXTAREA =====
    document.querySelectorAll('textarea').forEach(textarea => {
        textarea.addEventListener('input', function () {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 200) + 'px';
        });
    });

    // ===== HISTORY =====
    if (!history.state) {
        history.replaceState({ path: '/' }, '', '/');
    }
});


// ===== ЮРИДИЧЕСКАЯ ПОМОЩЬ: сервер → файловый MCP → ответ =====
let legalReady = false;
let legalMode = 'unknown';
const legalClient = new LegalClient({
    onState(chatId, busy) {
        if (state.activeChatId === chatId) document.getElementById('chatSendBtn').disabled = busy || !legalReady;
    },
    async onResult(chatId, requestId, result) {
        const chat = state.chats.find(item => item.id === chatId);
        if (!chat) return; // Deleted chat must never be recreated by a late response.
        const reply = chat.messages.find(item => item.legal?.requestId === requestId);
        if (!reply) return;
        LegalPrivacy.finishUpdate(reply, result, requestId);
        await ChatDB.saveChat(chat);
        if (state.activeChatId === chatId) renderMessages(chat);
        renderChatList();
    }
});

async function connectLegal() {
    const banner = document.getElementById('legalMode');
    try {
        const response = await fetch('/api/legal-help/config');
        if (!response.ok) throw new Error('Нет соединения');
        const config = await response.json();
        legalMode = config.mode;
        banner.textContent = config.notice;
        banner.dataset.mode = legalMode;
        legalReady = true;
        // Pending requests do not survive a browser restart. Offer an explicit retry.
        for (const chat of state.chats) {
            for (const msg of chat.messages || []) {
                if (msg.legal?.status === 'pending' || msg.legal?.updating) {
                    LegalPrivacy.finishUpdate(msg, {status:'error', answer:'Предыдущее ожидание прервано перезагрузкой страницы. Можно повторить запрос.'}, msg.legal.requestId);
                    await ChatDB.saveChat(chat);
                }
            }
        }
    } catch (error) {
        banner.textContent = 'Сервер юридической помощи недоступен. Запустите приложение по инструкции; открытие HTML-файла отдельно не подключает модель.';
        banner.dataset.mode = 'error';
    }
    document.getElementById('startSendBtn').disabled = !legalReady;
    document.getElementById('chatSendBtn').disabled = !legalReady;
}

async function startLegal(chat, userMessage, intake) {
    if (!legalReady || legalClient.busy(chat.id) || !state.chats.includes(chat)) return;
    if (!userMessage.id) userMessage.id = generateChatId();
    if (intake) userMessage.intake = intake;
    let reply = chat.messages.find(item => item.legal?.requestId === userMessage.id);
    if (!reply) {
        reply = {role: 'assistant', text: '', attachments: [], legal: {requestId: userMessage.id}};
        chat.messages.push(reply);
    }
    LegalPrivacy.beginUpdate(reply, userMessage.id, legalMode);
    await ChatDB.saveChat(chat);
    if (state.activeChatId === chat.id) renderMessages(chat);
    return legalClient.submit({chatId: chat.id, requestId: userMessage.id, question: userMessage.text,
        history: LegalPrivacy.chatHistory(chat, userMessage.id), intake: userMessage.intake || {}, attachments: userMessage.attachments || []});
}

function actionButton(text, handler) {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'legal-action'; button.textContent = text;
    button.addEventListener('click', handler);
    return button;
}

function renderLegalMessage(container, chat, message) {
    const data = message.legal;
    const user = chat.messages.find(item => item.id === data.requestId && item.role === 'user');
    const status = document.createElement('div');
    status.className = 'legal-status';
    const labels = {pending: 'Обработка', answered: 'Готово', partial_answer: 'Предварительный ответ', needs_clarification: 'Нужны исходные сведения',
        insufficient_sources: 'Недостаточно данных', unsupported: 'Функция не подключена', error: 'Ошибка', invalid_request: 'Проверьте ввод', cancelled: 'Ожидание отменено'};
    status.textContent = (data.updating ? 'Обновление ответа' : (labels[data.status] || '')) + (data.mode === 'demo' ? ' · Учебный режим, без LLM' : '');
    container.appendChild(status);
    if (data.updateFailed) {
        const notice = document.createElement('p'); notice.className = 'legal-update-notice';
        notice.textContent = 'Не удалось обновить ответ. Показана предыдущая версия — новые уточнения в ней не учтены.';
        container.appendChild(notice);
    }
    if (data.status === 'pending' || data.updating) {
        container.appendChild(actionButton('Отменить ожидание', async () => {
            legalClient.cancel(chat.id); LegalPrivacy.finishUpdate(message, {status:'cancelled',answer:'Ожидание отменено. Автоматический повтор не выполняется.'}, data.requestId);
            await ChatDB.saveChat(chat); if (state.activeChatId === chat.id) renderMessages(chat);
        }));
    }
    if (['needs_clarification','partial_answer'].includes(data.status) && user && data.missing_fields?.length) {
        const form = document.createElement('form'); form.className = 'legal-intake';
        const intro = document.createElement('p');
        const optional = data.status === 'partial_answer';
        intro.textContent = optional ? 'Если знаете эти сведения, укажите их для уточнения ответа. Можно заполнить только часть полей или оставить предварительный ответ.' : 'Опишите, с каким вопросом нужна помощь. Достаточно ситуации или желаемого результата.';
        form.appendChild(intro);
        for (const field of data.missing_fields) {
            const label = document.createElement('label'); label.textContent = field.label;
            const input = document.createElement('textarea');
            input.name = field.key; input.required = false; input.maxLength = 3000; input.rows = 2;
            input.value = data.intakeDraft?.[field.key] || user.intake?.[field.key] || (field.key === 'situation' ? user.text : '');
            input.addEventListener('input', () => {
                data.intakeDraft = {...(data.intakeDraft || {}), [field.key]: input.value};
            });
            label.appendChild(input); form.appendChild(label);
        }
        const submit = document.createElement('button'); submit.type = 'submit'; submit.className = 'legal-action'; submit.textContent = optional ? 'Уточнить ответ' : 'Передать сведения и выполнить';
        form.appendChild(submit);
        form.addEventListener('submit', event => {
            event.preventDefault();
            if (legalClient.busy(chat.id)) return;
            const intake = {...(user.intake || {})};
            let changed = false;
            for (const input of form.querySelectorAll('textarea')) {
                const value = input.value.trim();
                if (value && value !== (intake[input.name] || (input.name === 'situation' ? user.text : ''))) { intake[input.name] = value; changed = true; }
            }
            if (!changed) { intro.textContent = 'Добавьте хотя бы одно новое сведение. Если ничего не известно, текущий ответ остаётся доступным.'; return; }
            submit.disabled = true;
            startLegal(chat, user, intake);
        });
        container.appendChild(form);
    }
    if ((data.updateFailed || ['error','cancelled','insufficient_sources'].includes(data.status)) && !data.updating && user && !user.attachments?.length) {
        container.appendChild(actionButton('Повторить запрос', () => startLegal(chat, user)));
    }
    if (data.source_checked_at) {
        const checked = document.createElement('p'); checked.className = 'legal-source-date';
        checked.textContent = 'Нормативные материалы проверены: ' + new Date(data.source_checked_at).toLocaleString('ru-RU', {timeZone:'Europe/Moscow'});
        container.appendChild(checked);
    }
    const failedTasks = (data.task_outcomes || []).filter(task => ['error','insufficient_sources'].includes(task.status));
    for (const task of failedTasks) {
        const note = document.createElement('p'); note.className = 'legal-task-outcome'; note.textContent = 'Не разобрана часть запроса: ' + task.summary; container.appendChild(note);
    }
    if (data.legal_bases?.length) {
        const section = document.createElement('div'); section.className = 'legal-grounds';
        const heading = document.createElement('strong'); heading.textContent = 'Правовые основания'; section.appendChild(heading);
        for (const basis of data.legal_bases) {
            const paragraph = document.createElement('p');
            paragraph.textContent = `${basis.title}, ${basis.article} — ${basis.explanation}`;
            section.appendChild(paragraph);
        }
        container.appendChild(section);
    }
    if (data.limitations?.length) {
        const limits = document.createElement('p'); limits.className = 'legal-limitations'; limits.textContent = data.limitations.join(' '); container.appendChild(limits);
    }

}
