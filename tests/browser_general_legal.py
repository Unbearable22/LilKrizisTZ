"""No paid calls: verify general-law fields, checked date, partial outcomes and storage."""
import asyncio
from playwright.async_api import async_playwright
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,args=['--no-sandbox']);page=await browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));calls=0
  async def respond(route):
   nonlocal calls
   calls+=1;q=route.request.post_data_json
   if calls==1:r={'status':'partial_answer','answer':'Если обстоятельства подтвердятся, можно уточнить порядок защиты.','missing_fields':[{'key':'event_date','label':'Когда это произошло, если знаете'}],'source_checked_at':'2026-10-22T09:00:00+00:00','legal_bases':[{'title':'Трудовой кодекс Российской Федерации','article':'Статья 136','explanation':'Определяет порядок выплаты.'}],'task_outcomes':[{'task_id':'a','status':'answered','summary':'Оплата труда'},{'task_id':'b','status':'error','summary':'Другой вопрос'}]}
   else:r={'status':'error','answer':'Источник недоступен.','source_checked_at':'2026-10-23T09:00:00+00:00'}
   await route.fulfill(json={**r,'chat_id':q['chat_id'],'mode':'demo'})
  await page.route('**/api/legal-help',respond);await page.goto('http://127.0.0.1:8082')
  await page.locator('#startInput').fill('Мне не платят зарплату, дату не помню');await page.locator('#startSendBtn').click()
  await page.locator('.legal-source-date').wait_for();assert '22.10.2026' in await page.locator('.legal-source-date').inner_text()
  assert await page.locator('textarea[name=object_reference]').count()==0
  assert await page.locator('.legal-task-outcome').count()==1
  await page.locator('.legal-intake textarea').fill('не знаю');await page.locator('.legal-intake button').click()
  await page.locator('.legal-update-notice').wait_for();assert '22.10.2026' in await page.locator('.legal-source-date').inner_text()
  await page.reload();await page.locator('.chat-item').first.click();await page.locator('.legal-update-notice').wait_for()
  assert '22.10.2026' in await page.locator('.legal-source-date').inner_text();assert await page.locator('.legal-grounds').count()==1
  assert not errors,errors
  await browser.close();print('PASS: general fields, date, task error, old verification date on update failure/reload')
asyncio.run(main())
