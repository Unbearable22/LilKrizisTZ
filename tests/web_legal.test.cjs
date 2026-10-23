const {test}=require('node:test');
const assert=require('node:assert/strict');
let LegalClient;
try{({LegalClient}=require('../groundAndLaw/legal-api.js'));}catch{}

test('request result stays bound to original chat and source message',async()=>{
 assert.equal(typeof LegalClient,'function','Клиент юридического API ещё не реализован');
 let finish;const updates=[];
 const client=new LegalClient({fetch:()=>new Promise(r=>{finish=r}),onResult:(...v)=>updates.push(v)});
 const promise=client.submit({chatId:'first',requestId:'message1',question:'Вопрос',intake:{}});
 finish({ok:true,json:async()=>({status:'answered',chat_id:'first',answer:'Ответ',sources:[]})});
 await promise;assert.equal(updates[0][0],'first');assert.equal(updates[0][1],'message1');
});

test('cancelled or deleted chat never receives a late response',async()=>{
 assert.equal(typeof LegalClient,'function');let finish;let writes=0;
 const client=new LegalClient({fetch:()=>new Promise(r=>{finish=r}),onResult:()=>writes++});
 const promise=client.submit({chatId:'gone',requestId:'m',question:'Вопрос'});
 client.cancel('gone');
 finish({ok:true,json:async()=>({status:'answered',chat_id:'gone',sources:[]})});
 await promise;assert.equal(writes,0);
});

test('API error is shown and a later retry can succeed',async()=>{
 assert.equal(typeof LegalClient,'function');let calls=0;const results=[];
 const client=new LegalClient({fetch:async()=>++calls===1?{ok:false,json:async()=>({answer:'Ошибка сервиса'})}:{ok:true,json:async()=>({status:'answered',chat_id:'a',sources:[]})},onResult:(c,m,r)=>results.push(r)});
 await client.submit({chatId:'a',requestId:'m',question:'Вопрос'});
 assert.equal(results[0].status,'error');
 await client.submit({chatId:'a',requestId:'m',question:'Вопрос'});
 assert.equal(results[1].status,'answered');
});

test('attachments and concurrent duplicate sends do not trigger ignored input or duplicate calls',async()=>{
 assert.equal(typeof LegalClient,'function');let calls=0;let finish;const results=[];
 const client=new LegalClient({fetch:()=>{calls++;return new Promise(r=>finish=r)},onResult:(c,m,r)=>results.push(r)});
 await client.submit({chatId:'a',requestId:'file',question:'Вопрос',attachments:[{name:'proof.pdf'}]});
 assert.equal(calls,0);assert.equal(results[0].status,'error');
 const first=client.submit({chatId:'a',requestId:'m',question:'Вопрос'});
 await client.submit({chatId:'a',requestId:'m',question:'Вопрос'});
 assert.equal(calls,1);
 finish({ok:true,json:async()=>({status:'answered',chat_id:'a',sources:[]})});await first;
});

test('mismatched API chat id is rejected instead of displayed',async()=>{
 assert.equal(typeof LegalClient,'function');const results=[];
 const client=new LegalClient({fetch:async()=>({ok:true,json:async()=>({status:'answered',chat_id:'other',answer:'Чужой ответ'})}),onResult:(c,m,r)=>results.push(r)});
 await client.submit({chatId:'a',requestId:'m',question:'Вопрос'});
 assert.equal(results[0].status,'error');assert.notEqual(results[0].answer,'Чужой ответ');
});

test('transport never passes private source fields to UI or persistence',async()=>{
 const updates=[];
 const client=new LegalClient({fetch:async()=>({ok:true,json:async()=>({status:'answered',chat_id:'a',answer:'Ответ без ссылок.',sources:[{title:'Секретный реестр'}],citations:['private'],trace:['mcp.read'],tasks:[{source_url:'private'}],limitations:[]})}),onResult:(c,m,r)=>updates.push(r)});
 await client.submit({chatId:'a',requestId:'m',question:'Вопрос'});
 for(const key of ['sources','citations','trace','tasks'])assert.equal(key in updates[0],false,key);
});

test('legacy assistant sources are removed without changing original user question',()=>{
 const {cleanChat}=require('../groundAndLaw/legal-api.js');
 assert.equal(typeof cleanChat,'function');
 const old={id:'old',messages:[{role:'user',text:'Что означает статья 12 ЗК РФ?',id:'u'},
 {role:'assistant',text:'См. статью 12 ЗК РФ https://example.org.',legal:{requestId:'u',status:'answered',sources:[{title:'ЗК РФ'}],trace:['mcp'],answer:'См. статью 12 ЗК РФ.'}}]};
 const cleaned=cleanChat(old);
 assert.equal(cleaned.messages[0].text,'Что означает статья 12 ЗК РФ?');
 assert.doesNotMatch(JSON.stringify(cleaned.messages[1]),/https:|ЗК РФ|sources|trace/);
 assert.equal(cleaned.messages[1].legal.requestId,'u');
});

test('additional normative references never reach public answers',()=>{
 const {publicResult}=require('../groundAndLaw/legal-api.js');
 for(const answer of ['Согласно пункту 2 указанной нормы.','Согласно ГК РФ.','Согласно Федеральному закону о садоводстве.','См. закон о садоводстве.','Основание — Закон Российской Федерации о приватизации.','Согласно Гражданскому кодексу.'])assert.equal(publicResult({status:'answered',answer}).status,'error');
});

test('generic mentions of legislation do not erase a valid answer',()=>{
 const {publicResult}=require('../groundAndLaw/legal-api.js');
 for(const answer of ['Это предусмотрено федеральным законом.','Федеральными законами могут устанавливаться дополнительные условия.'])assert.equal(publicResult({status:'answered',answer}).status,'answered');
});

test('named regulations and orders are not public answer text',()=>{
 const {publicResult}=require('../groundAndLaw/legal-api.js');
 for(const answer of ['Согласно постановлению Правительства РФ от 28.01.2006 № 47.','Согласно приказу Минэкономразвития России от 08.12.2015 № 921.'])assert.equal(publicResult({status:'answered',answer}).status,'error');
});

test('transport accepts preliminary answers and optional clarification fields',async()=>{
 const results=[];
 const client=new LegalClient({fetch:async()=>({ok:true,json:async()=>({chat_id:'a',status:'partial_answer',answer:'Если условие выполнено, можно уточнить порядок.',missing_fields:[{key:'rights',label:'Права на участок'}]})}),onResult:(c,m,r)=>results.push(r)});
 await client.submit({chatId:'a',requestId:'m',question:'Вопрос'});
 assert.equal(results[0].status,'partial_answer');assert.equal(results[0].missing_fields[0].key,'rights');
});

test('history includes only preceding client messages from selected chat',()=>{
 const {chatHistory}=require('../groundAndLaw/legal-api.js');
 const chat={messages:[{id:'a',role:'user',text:'Участок мой',intake:{rights:'собственность'}},{role:'assistant',text:'Ответ'},{id:'b',role:'user',text:'Как защитить?'},{id:'c',role:'user',text:'Позднее сообщение'}]};
 assert.deepEqual(chatHistory(chat,'b'),[{text:'Участок мой',intake:{rights:'собственность'}}]);
});
test('verified structured legal grounds survive persistence without exposing private ids',()=>{
 const {publicResult,cleanChat}=require('../groundAndLaw/legal-api.js');
 const bases=[{title:'Земельный кодекс РФ',article:'Статья 56.3',explanation:'Определяет основания изъятия.',fragment_id:'private'}];
 const result=publicResult({status:'answered',answer:'Значимы основания изъятия.',legal_bases:bases});
 assert.equal(result.legal_bases[0].article,'Статья 56.3');
 assert.equal(result.legal_bases[0].fragment_id,undefined);
 assert.deepEqual(cleanChat({messages:[{role:'assistant',text:result.answer,legal:result}]}).messages[0].legal.legal_bases,result.legal_bases);
});

test('confirmed article in answer is displayed and survives reload sanitization',()=>{
 const {publicResult,cleanChat}=require('../groundAndLaw/legal-api.js');
 const result={status:'answered',answer:'Условия определяет статья 56.3 Земельного кодекса Российской Федерации.',legal_bases:[{title:'Земельный кодекс Российской Федерации',article:'Статья 56.3. Условия изъятия',explanation:'Определяет условия.'}]};
 assert.equal(publicResult(result).status,'answered');
 assert.equal(cleanChat({messages:[{role:'assistant',text:result.answer,legal:result}]}).messages[0].text,result.answer);
 assert.equal(publicResult({...result,answer:'См. статью 999 ЗК РФ.'}).status,'error');
});

test('failed update preserves last successful answer and legal grounds across storage cleaning',()=>{
 const {beginUpdate,finishUpdate,cleanChat}=require('../groundAndLaw/legal-api.js');
 const reply={role:'assistant',text:'Первый ответ.',legal:{requestId:'q',status:'partial_answer',answer:'Первый ответ.',legal_bases:[{title:'Учебный акт',article:'Статья 1',explanation:'Определяет условия.'}],missing_fields:[{key:'rights',label:'Права'}]}};
 beginUpdate(reply,'q','live');assert.equal(reply.text,'Первый ответ.');assert.equal(reply.legal.updating,true);
 finishUpdate(reply,{status:'error',answer:'Сбой модели.'},'q');
 assert.equal(reply.text,'Первый ответ.');assert.equal(reply.legal.updateFailed,true);assert.equal(reply.legal.updating,false);
 const stored=cleanChat(JSON.parse(JSON.stringify({messages:[reply]}))).messages[0];
 assert.equal(stored.text,'Первый ответ.');assert.equal(stored.legal.updateFailed,true);assert.equal(stored.legal.legal_bases.length,1);
 beginUpdate(stored,'q','live');finishUpdate(stored,{status:'error',answer:'Ещё сбой.'},'q');assert.equal(stored.text,'Первый ответ.');
 beginUpdate(stored,'q','live');finishUpdate(stored,{status:'answered',answer:'Обновлённый ответ.'},'q');assert.equal(stored.text,'Обновлённый ответ.');assert.equal(!!stored.legal.updateFailed,false);
});
test('first failure and another request do not reuse an unrelated answer',()=>{
 const {beginUpdate,finishUpdate}=require('../groundAndLaw/legal-api.js');
 const reply={role:'assistant',text:'Чужой ответ.',legal:{requestId:'old',status:'answered',answer:'Чужой ответ.'}};
 beginUpdate(reply,'new','live');finishUpdate(reply,{status:'error',answer:'Ошибка.'},'new');
 assert.equal(reply.text,'Ошибка.');assert.equal(reply.legal.status,'error');assert.equal(!!reply.legal.updateFailed,false);
});

test('source date and partial task outcomes persist; failed update keeps old verification date',()=>{
 const {publicResult,beginUpdate,finishUpdate,cleanChat}=require('../groundAndLaw/legal-api.js');
 const result=publicResult({status:'partial_answer',answer:'Предварительный ответ.',source_checked_at:'2026-10-22T09:00:00+00:00',task_outcomes:[{task_id:'t1',status:'answered',summary:'Трудовой вопрос',trace:'private'},{task_id:'t2',status:'error',summary:'Другая часть'}]});
 assert.equal(result.source_checked_at,'2026-10-22T09:00:00+00:00');assert.equal(result.task_outcomes[0].trace,undefined);
 const reply={role:'assistant',text:result.answer,legal:{...result,requestId:'q'}};
 beginUpdate(reply,'q','live');finishUpdate(reply,{status:'error',answer:'Не удалось.',source_checked_at:'2026-10-23T09:00:00+00:00'},'q');
 assert.equal(cleanChat({messages:[reply]}).messages[0].legal.source_checked_at,result.source_checked_at);
});

test('new legal code names checked and warranty does not collide with provider name',()=>{
 const {publicResult}=require('../groundAndLaw/legal-api.js');
 const b=[{title:'Трудовой кодекс Российской Федерации',article:'Статья 136',explanation:'Определяет сроки.'}];
 assert.equal(publicResult({status:'answered',answer:'Статья 136 ТК РФ.',legal_bases:b}).status,'answered');
 assert.equal(publicResult({status:'answered',answer:'Статья 136 СК РФ.',legal_bases:b}).status,'error');
 assert.equal(publicResult({status:'answered',answer:'Гарантийный срок и гарантия качества.'}).status,'answered');
});
