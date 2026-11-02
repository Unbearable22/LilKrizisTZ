"""Real browser contract: answers and stored history without references. Start web first."""
import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright


async def main():
    base=next((arg for arg in sys.argv[1:] if arg.startswith('http')),'http://127.0.0.1:8081')
    mode='live' if '--live' in sys.argv else 'demo'
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=['--no-sandbox'])
        page=await browser.new_page(viewport={'width':1360,'height':900});page.set_default_timeout(130000)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(base);await page.locator(f'#legalMode[data-mode={mode}]').wait_for()
        await page.locator('#startInput').fill('Какими способами образуются земельные участки?')
        await page.locator('#startSendBtn').click()
        await page.locator('.legal-status').filter(has_text='Готово').wait_for()
        assert await page.locator('.message.user').count()==1
        assert await page.locator('.legal-intake').count()==0
        assert await page.locator('.legal-source, details').count()==0
        assistant=page.locator('.message:not(.user)')
        assert not await assistant.locator('a').count()
        await page.screenshot(path='data/client-stage/web-desktop.png',full_page=True)
        await page.reload();await page.locator(f'#legalMode[data-mode={mode}]').wait_for();await page.locator('.chat-item').first.click()
        await page.locator('.legal-status').filter(has_text='Готово').wait_for()
        print('Browser: clear question -> real MCP -> answer without intake -> reload: PASS',flush=True)
        await page.locator('#chatInput').fill('Можно ли построить жилой дом на моём земельном участке? Разрешённое использование не знаю.')
        await page.locator('#chatSendBtn').click()
        await page.locator('.legal-status').filter(has_text='Предварительный ответ').wait_for()
        form=page.locator('.legal-intake');await form.wait_for()
        fields=form.locator('textarea')
        assert 1<=await fields.count()<=3
        assert not await fields.first.evaluate('(node)=>node.required')
        await form.locator('button[type=submit]').click()
        await form.get_by_text('Добавьте хотя бы одно новое сведение.',exact=False).wait_for()
        await fields.first.fill('не знаю')
        await form.locator('button[type=submit]').click()
        await page.locator('.legal-status').filter(has_text='Обновление ответа').wait_for()
        await page.locator('.legal-status').filter(has_text='Предварительный ответ').wait_for()
        assert await page.locator('.message.user').count()==2
        await page.reload();await page.locator(f'#legalMode[data-mode={mode}]').wait_for();await page.locator('.chat-item').first.click()
        await page.locator('.legal-status').filter(has_text='Предварительный ответ').wait_for()
        print('Browser: conditional answer -> optional single-field unknown -> answer -> reload: PASS',flush=True)
        # Seed the old storage shape directly to exercise actual migration on startup.
        await page.evaluate('''async () => {
            const db=await new Promise((resolve,reject)=>{const r=indexedDB.open('groundandlaw',1);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error)});
            await new Promise((resolve,reject)=>{const t=db.transaction('chats','readwrite');t.objectStore('chats').put({id:'legacy',title:'Старый диалог',updatedAt:Date.now()+1000,messages:[{id:'u',role:'user',text:'Что означает статья 12 ЗК РФ?'},{role:'assistant',text:'См. статью 12 ЗК РФ https://example.org',legal:{requestId:'u',status:'answered',sources:[{title:'ЗК РФ',source_url:'https://example.org'}],trace:['mcp.read'],answer:'См. статью 12 ЗК РФ'}}]});t.oncomplete=resolve;t.onerror=()=>reject(t.error)});db.close();
        }''')
        await page.reload();await page.locator(f'#legalMode[data-mode={mode}]').wait_for();await page.locator('.chat-item[data-chat-id=legacy]').click()
        await page.get_by_text('Сохранённый ответ нужно обновить.',exact=False).wait_for()
        stored=await page.evaluate('''async () => {
            const db=await new Promise(resolve=>{const r=indexedDB.open('groundandlaw',1);r.onsuccess=()=>resolve(r.result)});
            const value=await new Promise(resolve=>{const r=db.transaction('chats').objectStore('chats').get('legacy');r.onsuccess=()=>resolve(r.result)});db.close();return value;
        }''')
        assert stored['messages'][0]['text']=='Что означает статья 12 ЗК РФ?'
        serialized=json.dumps(stored['messages'][1],ensure_ascii=False)
        assert all(word not in serialized for word in ('sources','trace','source_url','https://','ЗК РФ'))
        print('Browser: legacy IndexedDB metadata and answer migrated; user original preserved: PASS',flush=True)
        await page.set_viewport_size({'width':390,'height':844})
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        await page.screenshot(path='data/client-stage/web-mobile.png',full_page=True)
        assert not errors,errors
        print('Browser: mobile viewport and no JavaScript errors: PASS',flush=True)
        await browser.close()

if __name__=='__main__':asyncio.run(main())
