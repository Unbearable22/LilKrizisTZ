"""Browser regression: preserve a validated answer when updating fails."""
import asyncio
import sys
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=['--no-sandbox'])
        page=await browser.new_page();page.set_default_timeout(15000)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        calls=0;release=asyncio.Event()
        async def respond(route):
            nonlocal calls
            calls+=1;n=calls;payload=route.request.post_data_json
            if n==5:
                await release.wait()
                try:await route.abort()
                except Exception:pass
                return
            if n in (2,3,6):
                await route.fulfill(status=502 if n==2 else 200,json={'chat_id':payload['chat_id'],'status':'error','answer':'Сервис недоступен.'})
                return
            await route.fulfill(json={'chat_id':payload['chat_id'],'status':'partial_answer','answer':'Первый успешный ответ.' if n==1 else 'Новый успешный ответ.','missing_fields':[{'key':'rights' if n==1 else 'documents','label':'Уточните сведения'}],'legal_bases':[{'title':'Учебный акт','article':'Статья 1','explanation':'Определяет условия.'}]})
        await page.route('**/api/legal-help',respond)
        await page.goto((next((arg for arg in sys.argv[1:] if arg.startswith('http')),'http://127.0.0.1:8080')))
        await page.locator('#startInput').fill('Вопрос про мой участок');await page.locator('#startSendBtn').click()
        await page.get_by_text('Первый успешный ответ.',exact=True).wait_for()
        await page.locator('.legal-intake textarea').fill('Собственность');await page.locator('.legal-intake button').click()
        await page.locator('.legal-update-notice').wait_for()
        assert await page.get_by_text('Первый успешный ответ.',exact=True).count()==1
        assert await page.locator('.legal-grounds').count()==1
        await page.reload();await page.locator('.chat-item').first.click();await page.locator('.legal-update-notice').wait_for()
        assert await page.get_by_text('Первый успешный ответ.',exact=True).count()==1
        await page.get_by_role('button',name='Повторить запрос',exact=True).click()
        await page.locator('.legal-update-notice').wait_for()
        assert await page.get_by_text('Первый успешный ответ.',exact=True).count()==1
        await page.get_by_role('button',name='Повторить запрос',exact=True).click()
        await page.get_by_text('Новый успешный ответ.',exact=True).wait_for()
        assert await page.locator('.legal-update-notice').count()==0
        await page.locator('.legal-intake textarea').fill('Есть выписка');await page.locator('.legal-intake button').click()
        await page.get_by_text('Обновление ответа',exact=True).wait_for()
        assert await page.get_by_text('Новый успешный ответ.',exact=True).count()==1
        await page.reload();release.set();await page.locator('.chat-item').first.click()
        await page.locator('.legal-update-notice').wait_for()
        assert await page.get_by_text('Новый успешный ответ.',exact=True).count()==1
        await page.locator('#newChatBtn').click();await page.locator('#startInput').fill('Другой вопрос')
        await page.locator('#startSendBtn').click();await page.get_by_text('Сервис недоступен.',exact=True).wait_for()
        assert await page.locator('.legal-update-notice,.legal-grounds').count()==0
        assert not errors,errors
        await browser.close()
        print('PASS: HTTP 502 and model error preserve answer; reload; repeated failure; successful replacement; reload during pending; new question has no unrelated fallback')
asyncio.run(main())
