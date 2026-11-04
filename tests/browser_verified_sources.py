"""Browser-only fixtures: safe links, IndexedDB, failed clarification and old chats."""
import asyncio
import os
from playwright.async_api import async_playwright
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,args=['--no-sandbox']);page=await browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));calls=0
  source={'number':1,'title':'Трудовой кодекс Российской Федерации','publisher':'КонсультантПлюс','source_kind':'normative_act','url':'https://www.consultant.ru/document/cons_doc_LAW_34683/','citation':'Статья 136','revision':'ред. от 01.01.2026','checked_at':'2026-11-02T09:00:00+00:00'}
  async def respond(route):
   nonlocal calls
   calls+=1;q=route.request.post_data_json
   result={'status':os.getenv('TEST_RESPONSE_STATUS','partial_answer'),'answer':'Можно уточнить порядок защиты.','missing_fields':[{'key':'event_date','label':'Когда это произошло, если знаете'}],'evidence':[source],'legal_bases':[{'title':source['title'],'article':source['citation'],'explanation':'Определяет порядок выплаты.'}]} if calls==1 else {'status':'error','answer':'Источник недоступен.'}
   await route.fulfill(json={**result,'chat_id':q['chat_id'],'mode':'demo'})
  await page.route('**/api/legal-help',respond);await page.goto(os.getenv('TEST_WEB_URL','http://127.0.0.1:8082'))
  await page.locator('#startInput').fill('Мне не платят зарплату, дату не помню');await page.locator('#startSendBtn').click()
  link=page.locator('.legal-evidence a');await link.wait_for()
  assert await link.get_attribute('href')==source['url'];assert await link.get_attribute('rel')=='noopener noreferrer'
  await page.locator('.legal-intake textarea').fill('не знаю');await page.locator('.legal-intake button').click()
  await page.locator('.legal-update-notice').wait_for();assert await link.count()==1
  await page.reload();await page.locator('.chat-item').first.click();await link.wait_for()
  assert await link.get_attribute('href')==source['url'];assert not errors,errors
  await browser.close();print('PASS: verified links, failed clarification and IndexedDB reload')
asyncio.run(main())
