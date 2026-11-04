"""UI fixture: general guidance is visibly distinct and survives browser history."""
import asyncio,os
from playwright.async_api import async_playwright
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,args=['--no-sandbox']);page=await browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  async def respond(route):
   body=route.request.post_data_json
   await route.fulfill(json={'chat_id':body['chat_id'],'mode':'live','status':'partial_answer','response_kind':'general_guidance','answer':'Общая ориентировка — правовой вывод пока не подтверждён. Для подготовки соберите переписку и запишите хронологию.','missing_fields':[],'legal_bases':[],'evidence':[]})
  await page.route('**/api/legal-help',respond);await page.goto(os.getenv('TEST_WEB_URL','http://127.0.0.1:8080'))
  await page.locator('#startInput').fill('Не возвращают долг. Что делать?');await page.locator('#startSendBtn').click()
  status=page.locator('.legal-status');await status.wait_for();await page.get_by_text('Общая ориентировка',exact=True).wait_for()
  assert await page.get_by_role('button',name='Повторить проверку').count()==1
  assert await page.locator('.legal-evidence a').count()==0
  assert 'правовой вывод пока не подтверждён' in await page.locator('body').inner_text()
  await page.reload();await page.locator('.chat-item').first.click();await page.get_by_text('Общая ориентировка',exact=True).wait_for()
  assert not errors,errors
  await browser.close();print('PASS: guidance label, no false evidence and persisted history')
asyncio.run(main())
