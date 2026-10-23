"""Fake microphone/HTTP, no speech provider or paid model calls."""
import asyncio
from playwright.async_api import async_playwright
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,args=['--no-sandbox']);page=await browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  await page.add_init_script('''
   window.stopped=0;
   Object.defineProperty(navigator,'mediaDevices',{value:{getUserMedia:async()=>({getTracks:()=>[{stop:()=>window.stopped++}]})}});
   window.MediaRecorder=class {static isTypeSupported(){return true} constructor(){this.state='inactive';this.mimeType='audio/webm'} start(){this.state='recording'} stop(){this.state='inactive';this.ondataavailable({data:new Blob(['audio'],{type:'audio/webm'})});this.onstop()} };
  ''')
  count=0
  async def transcript(route):
   nonlocal count
   count+=1;await route.fulfill(json={'text':'У меня есть участок'})
  await page.route('**/api/transcribe',transcript)
  await page.goto('http://127.0.0.1:8080/')
  await page.locator('#startInput').fill('Здравствуйте.')
  await page.locator('#startMicBtn').click();await page.locator('#startMicBtn[aria-pressed=true]').wait_for()
  await page.locator('#startMicBtn').click()
  await page.wait_for_function("document.querySelector('#startInput').value.includes('есть участок')")
  assert await page.locator('#startInput').input_value()=='Здравствуйте. У меня есть участок'
  assert await page.locator('.message').count()==0
  assert await page.evaluate('window.stopped')==1
  await page.locator('#startMicBtn').click();await page.locator('#startMicBtn[aria-pressed=true]').wait_for();await page.locator('#startVoiceCancel').click()
  assert count==1
  await page.evaluate("() => {navigator.mediaDevices.getUserMedia=async()=>{throw Object.assign(new Error(),{name:'NotAllowedError'})};}")
  await page.locator('#startMicBtn').click();await page.wait_for_function("document.querySelector('#startVoiceStatus').textContent.includes('доступ')")
  assert not errors,errors
  await browser.close();print('PASS: microphone start/stop, editable appended text, no auto-send, cancel, permission error, tracks stopped')
asyncio.run(main())
