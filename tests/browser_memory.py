"""Browser integration with deterministic API replies; no paid model calls."""
import asyncio
import sys
import json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=['--no-sandbox'])
        page=await browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        requests=[]
        async def respond(route):
            payload=route.request.post_data_json;requests.append(payload)
            result={'chat_id':payload['chat_id'],'status':'partial_answer' if len(requests)==1 else 'answered','answer':'Условия определяет статья 1.','missing_fields':[{'key':'rights','label':'Права на участок'}] if len(requests)==1 else [],'limitations':[], 'legal_bases':[{'title':'Учебный акт','article':'Статья 1','explanation':'Определяет условия образования участка.'}]}
            await route.fulfill(json=result)
        await page.route('**/api/legal-help',respond)
        await page.goto((next((arg for arg in sys.argv[1:] if arg.startswith('http')),'http://127.0.0.1:8080')));await page.locator('#startSendBtn').wait_for(state='visible')
        await page.locator('#startInput').fill('Как образовать мой участок?');await page.locator('#startSendBtn').click()
        await page.locator('.legal-intake textarea').fill('собственность')
        await page.locator('.legal-intake button').click();await page.locator('.legal-status').filter(has_text='Готово').wait_for()
        await page.locator('#chatInput').fill('Какие действия дальше?');await page.locator('#chatSendBtn').click()
        await page.locator('.legal-status').filter(has_text='Готово').nth(1).wait_for()
        assert requests[0]['history']==[]
        assert requests[-1]['history']==[{'text':'Как образовать мой участок?','intake':{'rights':'собственность'}}], requests[-1]
        assert await page.locator('.legal-grounds').count()==2
        assert await page.get_by_text('Условия определяет статья 1.',exact=True).count()==2
        await page.reload();await page.locator('.chat-item').first.click()
        await page.locator('.legal-grounds').first.wait_for()
        assert await page.locator('.legal-grounds').count()==2
        assert await page.get_by_text('Условия определяет статья 1.',exact=True).count()==2
        await page.locator('#newChatBtn').click()
        await page.locator('#startInput').fill('Новый участок');await page.locator('#startSendBtn').click()
        await page.locator('.legal-status').filter(has_text='Готово').wait_for()
        assert requests[-1]['history']==[]
        assert not errors,errors
        print('PASS: submitted fields in next question; legal grounds persist after reload; chats isolated; no browser errors')
        await browser.close()
asyncio.run(main())
