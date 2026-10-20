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

        el.appendChild(avatarEl);
        el.appendChild(bubbleEl);
        container.appendChild(el);
    });

    container.scrollTop = container.scrollHeight;
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

    chat.messages.push({ role: 'user', text, attachments: savedAttachments });
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

    renderChatList();
    setTimeout(() => document.getElementById('startInput')?.focus(), 100);

    // ===== ОТПРАВКА С ГЛАВНОГО ЭКРАНА =====
    const startInput = document.getElementById('startInput');
    const startSendBtn = document.getElementById('startSendBtn');

    async function sendFromStart() {
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
        const text = chatInput.value.trim();
        const chat = state.chats.find(c => c.id === state.activeChatId);
        const hasAttachments = chat && chat.attachments && chat.attachments.length > 0;

        if ((!text && !hasAttachments) || state.activeChatId === null) return;

        chatSendBtn.disabled = true;
        try {
            await appendMessage(state.activeChatId, text);
            chatInput.value = '';
            chatInput.style.height = 'auto';
        } catch (err) {
            console.error('Ошибка сохранения сообщения:', err);
            alert('Не удалось сохранить сообщение.');
        } finally {
            chatSendBtn.disabled = false;
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