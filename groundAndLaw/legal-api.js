/* Transport with request ownership. No model key or MCP endpoint exists in the browser. */
(function(root){
    const baseReferencePattern = /№\s*\d|(?:постановлен[а-яё]*|приказ[а-яё]*|распоряжен[а-яё]*|указ[а-яё]*)\s+(?:Правительств[а-яё]*|Мин[а-яё]*|Президент[а-яё]*|[«"])|https?:\/\/|www\.|consultant\.ru|garant\.ru|pravo\.gov\.ru|(?:ЗК|ГрК|ГПК|ГК|ТК|СК|ЖК|НК|УК|УПК|АПК|КАС|КоАП)\s*РФ|(?:земельн[а-яё]*|градостроительн[а-яё]*|трудов[а-яё]*|семейн[а-яё]*|жилищн[а-яё]*|налогов[а-яё]*|уголовн[а-яё]*|арбитражн[а-яё]*|гражданск[а-яё]*(?:\s+процессуальн[а-яё]*)?)\s+кодекс[а-яё]*|(?:пункт[а-яё]*|подпункт[а-яё]*|часть|части|п\.)\s*\d|закон[а-яё]*\s+(?:[«"]|от\s+\d|№\s*\d|о(?=\s)|об(?=\s)|РФ|Российск[а-яё]*)|(?:статья|статьи|статье|статью|статей|ст\.)\s*\d|\d+\s*[-‑–]\s*ФЗ|\[[^\]\n]{1,100}\]|【[^】]+】|[a-z0-9_-]{1,60}:[a-f0-9]{16}:\d+|(?:источники|нормативные основания)\s*:|КонсультантПлюс|(?<![а-яё])ГАРАНТ(?![а-яё])/iu;
    const codePattern=/(?:(?:ЗК|ГрК|ГПК|ГК|ТК|СК|ЖК|НК|УК|УПК|АПК|КАС|КоАП)\s*РФ|(?:земельн[а-яё]*|градостроительн[а-яё]*|трудов[а-яё]*|семейн[а-яё]*|жилищн[а-яё]*|налогов[а-яё]*|уголовно[- ]процессуальн[а-яё]*|уголовн[а-яё]*|(?:арбитражн[а-яё]*|гражданск[а-яё]*)(?:\s+процессуальн[а-яё]*)?)\s+кодекс[а-яё]*(?:\s+Российской\s+Федерации|\s+РФ)?|кодекс[а-яё]*(?:\s+Российск[а-яё]*\s+Федерац[а-яё]*|\s+РФ)?\s+(?:об\s+административн[а-яё]*\s+правонарушен[а-яё]*|административн[а-яё]*\s+судопроизводств[а-яё]*))/giu;
    const referencePattern=new RegExp(baseReferencePattern.source+"|"+codePattern.source,"iu");

    function codeFamily(value){
        const text=value.toLowerCase();
        const abbreviations={'зк':'land','грк':'urban','гпк':'civil_procedure','гк':'civil','тк':'labor','ск':'family','жк':'housing','нк':'tax','ук':'criminal','упк':'criminal_procedure','апк':'arbitration','кас':'administrative_procedure','коап':'offenses'};
        for(const [abbreviation,family] of Object.entries(abbreviations))if(new RegExp(String.raw`(?:^|[^а-яё])${abbreviation}\s*рф`,'iu').test(text))return family;
        if(text.includes('правонарушен'))return 'offenses';
        if(text.includes('судопроизводств'))return 'administrative_procedure';
        if(text.includes('арбитражн'))return 'arbitration';
        for(const [marker,family] of [['гражданск','civil'],['уголовн','criminal']])if(text.includes(marker))return family+(text.includes('процессуальн')?'_procedure':'');
        for(const [marker,family] of [['земельн','land'],['градостроительн','urban'],['трудов','labor'],['семейн','family'],['жилищн','housing'],['налогов','tax']])if(text.includes(marker))return family;
        return null;
    }
    const legacyNotice = 'Сохранённый ответ нужно обновить. Повторите запрос, чтобы получить ответ в новом формате.';
    function hasReferences(text){return typeof text==='string' && referencePattern.test(text);}
    function hasUnverifiedReferences(text,bases=[]) {
        if(typeof text!=='string')return true;
        if(!bases.length)return hasReferences(text);
        let remaining=text;
        for(const basis of bases)remaining=remaining.split(basis.title).join(' ');
        remaining=remaining.replace(codePattern,name=>{
            const family=codeFamily(name);
            return family && bases.some(b=>codeFamily(b.title)===family)?' ':name;
        });
        const articles=new Set(bases.map(b=>b.article.match(/(?:Статья|ст\.)\s*(\d+(?:\.\d+)*)/iu)?.[1]).filter(Boolean));
        remaining=remaining.replace(/(?:статья|статьи|статье|статью|статей|ст\.)\s*(\d+(?:\.\d+)*)/giu,(whole,number)=>articles.has(number)?' ':whole);
        const numbers=new Set(bases.flatMap(b=>[...b.title.matchAll(/(\d+)\s*[-‑–]\s*ФЗ/giu)].map(m=>m[1])));
        remaining=remaining.replace(/(?:№\s*)?(\d+)\s*[-‑–]\s*ФЗ/giu,(whole,number)=>numbers.has(number)?' ':whole);
        return hasReferences(remaining);
    }
    function chatHistory(chat,messageId) {
        const index=chat.messages.findIndex(message=>message.id===messageId);
        return chat.messages.slice(0,index<0?0:index).filter(message=>message.role==='user')
            .map(message=>({text:message.text,intake:message.intake || {}}));
    }
    function publicResult(value={}) {
        const result={};
        for(const key of ['status','answer','mode','chat_id','requestId']) {
            if(typeof value[key]==='string')result[key]=value[key];
        }
        result.missing_fields=(Array.isArray(value.missing_fields)?value.missing_fields:[])
            .filter(item=>item && typeof item.key==='string' && typeof item.label==='string' && !hasReferences(item.key) && !hasReferences(item.label))
            .map(({key,label})=>({key,label}));
        result.limitations=(Array.isArray(value.limitations)?value.limitations:[]).filter(item=>typeof item==='string' && !hasReferences(item));
        result.legal_bases=(Array.isArray(value.legal_bases)?value.legal_bases:[])
            .filter(item=>item && ['title','article','explanation'].every(key=>typeof item[key]==='string' && item[key].length<=1000 && !/https?:\/\/|[a-z0-9_-]+:[a-f0-9]{16}:\d+/i.test(item[key])))
            .map(({title,article,explanation})=>({title,article,explanation}));
        if(typeof result.answer==='string' && hasUnverifiedReferences(result.answer,result.legal_bases)){result.answer=legacyNotice;result.status='error';}
        if(typeof value.source_checked_at==='string' && Number.isFinite(Date.parse(value.source_checked_at)))result.source_checked_at=value.source_checked_at;
        result.task_outcomes=(Array.isArray(value.task_outcomes)?value.task_outcomes:[]).filter(item=>item && typeof item.task_id==='string' && ['answered','partial_answer','error','insufficient_sources'].includes(item.status) && typeof item.summary==='string' && !/https?:\/\/|[a-z0-9_-]+:[a-f0-9]{16}:\d+/i.test(item.summary)).slice(0,4).map(({task_id,status,summary})=>({task_id,status,summary:summary.slice(0,500)}));
        for(const key of ['updating','updateFailed'])if(typeof value[key]==='boolean')result[key]=value[key];
        return result;
    }
    function successful(reply){return ['answered','partial_answer'].includes(reply.legal?.status) && !!reply.text?.trim();}
    function beginUpdate(reply,requestId,mode){
        if(reply.legal?.requestId===requestId && successful(reply)){
            reply.legal={...publicResult(reply.legal),requestId,updating:true,updateFailed:false};
        }else{
            reply.text='Готовлю ответ по доступным сведениям…';
            reply.legal={requestId,status:'pending',mode};
        }
    }
    function finishUpdate(reply,result,requestId){
        result=publicResult(result);
        if(reply.legal?.requestId===requestId && successful(reply) && ['error','invalid_request','cancelled','insufficient_sources'].includes(result.status)){
            reply.legal={...reply.legal,updating:false,updateFailed:true};
        }else{
            reply.text=result.answer || 'Ответ отсутствует.';
            reply.legal={...result,requestId};
        }
    }
    function cleanChat(chat) {
        if(!chat)return chat;
        return {...chat,messages:(chat.messages || []).map(msg=>{
            const {sources,citations,trace,tasks,...message}=msg;
            if(message.role==='assistant'){
                const known=msg.legal?.sources || [];
                const privateText=hasUnverifiedReferences(message.text,msg.legal?.legal_bases || []) || (!msg.legal?.legal_bases?.length && known.some(source=>source.title && message.text?.toLowerCase().includes(source.title.toLowerCase())));
                if(message.legal)message.legal=publicResult(message.legal);
                if(privateText){
                    message.text=legacyNotice;
                    if(message.legal){message.legal.status='error';message.legal.answer=legacyNotice;}
                }
            }
            return message;
        })};
    }
    root.LegalPrivacy={publicResult,cleanChat,chatHistory,beginUpdate,finishUpdate};
    class LegalClient {
        constructor({fetch:fetcher,onResult,onState}={}) {
            this.fetcher=fetcher || root.fetch.bind(root);
            this.onResult=onResult || (()=>{});
            this.onState=onState || (()=>{});
            this.pending=new Map();
        }
        busy(chatId){return this.pending.has(chatId);}
        cancel(chatId){
            const request=this.pending.get(chatId);
            if(request){this.pending.delete(chatId);request.controller.abort();this.onState(chatId,false);}
        }
        async submit({chatId,requestId,question,intake={},attachments=[],history=[]}){
            if(this.busy(chatId))return;
            if(attachments.length){
                await this.onResult(chatId,requestId,{status:'error',answer:'Анализ вложений пока не подключён. Уберите вложения и опишите сведения текстом; файл не использовался при анализе.',missing_fields:[]});
                return;
            }
            const controller=new AbortController();
            const request={controller};this.pending.set(chatId,request);this.onState(chatId,true);
            const timer=setTimeout(()=>controller.abort(),125000);
            try{
                const response=await this.fetcher('/api/legal-help',{
                    method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,
                    body:JSON.stringify({question,intake,chat_id:chatId,history})
                });
                const result=await response.json();
                if(this.pending.get(chatId)!==request)return;
                if(!response.ok)throw new Error(result.answer || 'Сервер не смог обработать запрос.');
                if(result.chat_id!==chatId)throw new Error('Ответ не соответствует исходному чату.');
                if(!['answered','partial_answer','needs_clarification','unsupported','insufficient_sources','error','invalid_request'].includes(result.status))throw new Error('Сервер вернул неизвестный результат.');
                await this.onResult(chatId,requestId,publicResult(result));
            }catch(error){
                if(this.pending.get(chatId)===request){
                    await this.onResult(chatId,requestId,publicResult({status:'error',answer:error.name==='AbortError'?'Истекло время ожидания. Автоматический повтор не выполнялся.':(error.message || 'Сервер недоступен.'),missing_fields:[]}));
                }
            }finally{
                clearTimeout(timer);
                if(this.pending.get(chatId)===request){this.pending.delete(chatId);this.onState(chatId,false);}
            }
        }
    }
    root.LegalClient=LegalClient;
    if(typeof module!=='undefined' && module.exports)module.exports={LegalClient,publicResult,cleanChat,chatHistory,beginUpdate,finishUpdate};
})(typeof window!=='undefined'?window:globalThis);
