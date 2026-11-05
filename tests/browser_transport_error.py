"""A blank gateway response produces a readable error and permits retry."""
import asyncio,os
from playwright.async_api import async_playwright

async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,args=['--no-sandbox'])
  page=await browser.new_page();errors=[];calls=0
  page.on('pageerror',lambda e:errors.append(str(e)))
  async def respond(route):
   nonlocal calls
   calls+=1
   if calls==1:await route.fulfill(status=502,body='');return
   payload=route.request.post_data_json
   await route.fulfill(json={'status':'partial_answer','chat_id':payload['chat_id'],'answer':'Тестовый ответ после восстановления соединения.','missing_fields':[]})
  await page.route('**/api/legal-help',respond)
  await page.goto(os.getenv('TEST_WEB_URL','http://127.0.0.1:8080'))
  await page.locator('#startInput').fill('Какие документы нужны для участка?')
  await page.locator('#startSendBtn').click()
  await page.get_by_text('Сервер не передал полный ответ:',exact=False).wait_for()
  assert 'Unexpected end' not in await page.locator('body').inner_text()
  assert calls==1
  await page.get_by_role('button',name='Повторить запрос',exact=True).click()
  await page.get_by_text('Тестовый ответ после восстановления соединения.',exact=False).wait_for()
  assert calls==2 and not errors,(calls,errors)
  await browser.close();print('PASS: empty 502, readable error, no automatic resend, successful manual retry')

asyncio.run(main())
