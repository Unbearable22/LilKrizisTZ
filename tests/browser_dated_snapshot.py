"""UI fixture: snapshot date remains visible in the response, source and history."""
import asyncio,os
from playwright.async_api import async_playwright
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,args=['--no-sandbox']);page=await browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  async def respond(route):
   body=route.request.post_data_json
   source={'title':'Земельный кодекс Российской Федерации','publisher':'КонсультантПлюс','source_kind':'normative_act','url':'https://www.consultant.ru/document/cons_doc_LAW_33773/','citation':'Статья 11.10','revision':'ред. 2026-08-04','checked_at':'2026-10-22','snapshot_as_of':'2026-10-22'}
   await route.fulfill(json={'chat_id':body['chat_id'],'mode':'live','status':'partial_answer','answer':'Сохранённые материалы проверены по состоянию на 22.10.2026. Изменения после этой даты не проверены. Общий разбор.','snapshot_as_of':'2026-10-22','source_checked_at':'2026-10-22','missing_fields':[],'evidence':[source]})
  await page.route('**/api/legal-help',respond);await page.goto(os.getenv('TEST_WEB_URL','http://127.0.0.1:8080'))
  await page.locator('#startInput').fill('Что такое схема участка?');await page.locator('#startSendBtn').click()
  await page.locator('.legal-source-date').wait_for()
  assert '22.10.2026' in await page.locator('.legal-source-date').inner_text()
  assert '00:00' not in await page.locator('.legal-source-date').inner_text()
  assert 'Сохранённая копия' in await page.locator('.legal-evidence').inner_text()
  await page.reload();await page.locator('.chat-item').first.click();await page.locator('.legal-evidence').wait_for()
  assert 'Сохранённая копия' in await page.locator('.legal-evidence').inner_text()
  assert '22.10.2026' in await page.locator('.legal-source-date').inner_text()
  assert not errors,errors
  await browser.close();print('PASS: snapshot response, source date without fake time and persisted history')
asyncio.run(main())
