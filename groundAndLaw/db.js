/**
 * ChatDB — обёртка над IndexedDB для хранения чатов.
 *
 * Схема БД:
 *   name:    'groundandlaw'
 *   version: 1
 *
 * Object store: 'chats'
 *   keyPath: 'id' (автоинкремент НЕ используем — id генерируем сами)
 *   Индекс:  'updatedAt' — чтобы сортировать по времени обновления
 *
 * Object store: 'files'
 *   keyPath: 'id' (уникальный id файла)
 *   Хранит:  { id, name, type, size, blob }
 *
 * Плюсы IndexedDB для файлов:
 *   - хранит Blob/File нативно, без base64 (+33% размера);
 *   - асинхронно — не блокирует UI.
 */
const ChatDB = (() => {
    const DB_NAME = 'groundandlaw';
    const DB_VERSION = 1;
    const STORE_CHATS = 'chats';
    const STORE_FILES = 'files';

    let dbPromise = null;

    // ===== Открытие БД =====
    function open() {
        if (dbPromise) return dbPromise;

        dbPromise = new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onupgradeneeded = (event) => {
                const db = event.target.result;

                // Хранилище чатов
                if (!db.objectStoreNames.contains(STORE_CHATS)) {
                    const chatsStore = db.createObjectStore(STORE_CHATS, { keyPath: 'id' });
                    chatsStore.createIndex('updatedAt', 'updatedAt', { unique: false });
                }

                // Хранилище файлов
                if (!db.objectStoreNames.contains(STORE_FILES)) {
                    db.createObjectStore(STORE_FILES, { keyPath: 'id' });
                }
            };

            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });

        return dbPromise;
    }

    // ===== Вспомогательная транзакция =====
    async function withStore(storeName, mode, callback) {
        const db = await open();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(storeName, mode);
            const store = tx.objectStore(storeName);
            const result = callback(store, tx);

            tx.oncomplete = () => resolve(result);
            tx.onerror = () => reject(tx.error);
            tx.onabort = () => reject(tx.error || new Error('Transaction aborted'));
        });
    }

    // ===== Промис-обёртка для запроса =====
    function requestToPromise(request) {
        return new Promise((resolve, reject) => {
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }

    // ============ FILES ============
    // Мы не храним File внутри чата — только ссылку (fileId).
    // Сами файлы лежат отдельно в STORE_FILES. Это позволяет:
    //   - не дублировать файлы между чатами;
    //   - чистить сироты (файлы без чатов).
    async function saveFile(file) {
        const id = `f_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
        const record = {
            id,
            name: file.name,
            type: file.type || 'application/octet-stream',
            size: file.size,
            blob: file
        };
        await withStore(STORE_FILES, 'readwrite', (store) => store.put(record));
        return { id, name: record.name, type: record.type, size: record.size };
    }

    async function getFile(id) {
        const db = await open();
        const tx = db.transaction(STORE_FILES, 'readonly');
        const store = tx.objectStore(STORE_FILES);
        const record = await requestToPromise(store.get(id));
        return record || null;
    }

    async function deleteFile(id) {
        await withStore(STORE_FILES, 'readwrite', (store) => store.delete(id));
    }

    async function getAllFileIds() {
        const db = await open();
        const tx = db.transaction(STORE_FILES, 'readonly');
        const store = tx.objectStore(STORE_FILES);
        const keys = await requestToPromise(store.getAllKeys());
        return keys;
    }

    // ============ CHATS ============
    async function saveChat(chat) {
        const toStore = { ...LegalPrivacy.cleanChat(chat), updatedAt: Date.now() };
        await withStore(STORE_CHATS, 'readwrite', (store) => store.put(toStore));
    }

    async function getChat(id) {
        const db = await open();
        const tx = db.transaction(STORE_CHATS, 'readonly');
        const store = tx.objectStore(STORE_CHATS);
        return LegalPrivacy.cleanChat(await requestToPromise(store.get(id)));
    }

    async function getAllChats() {
        const db = await open();
        const tx = db.transaction(STORE_CHATS, 'readonly');
        const store = tx.objectStore(STORE_CHATS);
        const all = await requestToPromise(store.getAll());
        // Remove legacy private metadata from stored history, not only its rendering.
        const cleaned=all.map(chat=>LegalPrivacy.cleanChat(chat));
        const changed=cleaned.filter((chat,index)=>JSON.stringify(chat)!==JSON.stringify(all[index]));
        if(changed.length)await withStore(STORE_CHATS,'readwrite',store=>{for(const chat of changed)store.put(chat);});
        // Сортировка: свежие сверху
        return cleaned.sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
    }

    async function deleteChat(id) {
        await withStore(STORE_CHATS, 'readwrite', (store) => store.delete(id));
    }

    // ============ УТИЛИТЫ ============
    /** Собрать все fileId, используемые в чатах */
    function collectUsedFileIds(chats) {
        const used = new Set();
        chats.forEach(chat => {
            (chat.messages || []).forEach(msg => {
                (msg.attachments || []).forEach(att => used.add(att.id));
            });
            (chat.attachments || []).forEach(att => used.add(att.id));
        });
        return used;
    }

    /** Удалить файлы, на которые никто не ссылается */
    async function cleanupOrphanFiles() {
        const chats = await getAllChats();
        const used = collectUsedFileIds(chats);
        const allFileIds = await getAllFileIds();

        const orphans = allFileIds.filter(id => !used.has(id));
        for (const id of orphans) {
            await deleteFile(id);
        }
        return orphans.length;
    }

    /** Очистить всё (на всякий случай — для отладки) */
    async function clearAll() {
        await withStore(STORE_CHATS, 'readwrite', (store) => store.clear());
        await withStore(STORE_FILES, 'readwrite', (store) => store.clear());
    }

    // ===== PUBLIC API =====
    return {
        open,
        saveFile,
        getFile,
        deleteFile,
        saveChat,
        getChat,
        getAllChats,
        deleteChat,
        cleanupOrphanFiles,
        clearAll
    };
})();
