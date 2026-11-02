import asyncio
import re
import logging
import time
import uuid
from .errors import LegalError
from .mcp_client import LocalLegalMCP
from .privacy import has_references, has_unverified_references
from .task_catalog import ALL_FIELDS,allowed_fields,validate_tasks,normalize_scope,search_query
from .consultant_mcp_client import ConsultantLegalMCP
from .consultant_types import RequestBudget,SourceError
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import os

FIELD_LABELS=ALL_FIELDS
GENERAL=('situation','goal')
UNKNOWN_FACTS={'не знаю','неизвестно','не известно','неизвестен','неизвестны','нет данных','не помню','пока не знаю','пока неизвестно'}


def valid_input(question,intake):
    if not isinstance(question,str) or not question.strip() or len(question)>8000:
        raise ValueError('Введите непустой вопрос длиной до 8000 символов.')
    if not isinstance(intake,dict) or set(intake)-set(FIELD_LABELS):raise ValueError('Некорректные поля анкеты.')
    if any(not isinstance(v,str) or len(v)>3000 for v in intake.values()):raise ValueError('Значения анкеты должны быть текстом до 3000 символов.')


def validate_plan(plan):return validate_tasks(plan)

def validate_answer(result,fragments,scope='general'):
    if not isinstance(result,dict) or not isinstance(result.get('answer'),str) or not result['answer'].strip() or len(result['answer'])>20000:
        raise LegalError('invalid_answer')
    if result.get('status','answered') not in ('answered','partial_answer','insufficient_sources'):raise LegalError('invalid_answer_status')
    if result.get('status')=='insufficient_sources':return
    if normalize_scope(scope)=='individual' and result.get('status','answered')=='answered':raise LegalError('definitive_parcel_answer')
    citations=result.get('citations')
    available={f['id']:f for f in fragments}
    if not isinstance(citations,list) or not citations or len(citations)>6 or any(not isinstance(c,str) or c not in available for c in citations):
        raise LegalError('invalid_citations')
    limits=result.get('limitations',[])
    if not isinstance(limits,list) or any(not isinstance(v,str) or len(v)>2000 for v in limits):raise LegalError('invalid_limitations')

    bases=result.get('legal_bases',[])
    if not isinstance(bases,list) or len(bases)>6:raise LegalError('invalid_legal_bases')
    for basis in bases:
        if not isinstance(basis,dict) or set(basis)!={'fragment_id','explanation'}:raise LegalError('invalid_legal_bases')
        if basis['fragment_id'] not in available:raise LegalError('invalid_citations')
        if not isinstance(basis['explanation'],str) or not 1<=len(basis['explanation'])<=400:raise LegalError('invalid_legal_bases')

    selected=[available[b['fragment_id']] for b in bases]
    check=(lambda text:has_unverified_references(text,selected)) if selected else (lambda text:has_references(text,fragments))
    if any(check(b['explanation']) for b in bases):raise LegalError('visible_references')
    if check(result['answer']) or any(check(limit) for limit in limits):raise LegalError('visible_references')

    if result.get('status')=='partial_answer':
        questions=result.get('missing_fields',[])
        if not isinstance(questions,list) or len(questions)>3 or any(not isinstance(k,str) or k not in FIELD_LABELS for k in questions) or len(set(questions))!=len(questions):raise LegalError('invalid_missing_fields')
        scenarios=result.get('scenarios')
        if not isinstance(scenarios,list) or not 1<=len(scenarios)<=3:raise LegalError('invalid_scenarios')
        for branch in scenarios:
            if not isinstance(branch,dict) or set(branch)!={'condition','outcome','citations'}:raise LegalError('invalid_scenarios')
            for key in ('condition','outcome'):
                if not isinstance(branch[key],str) or not branch[key].strip() or len(branch[key])>1200:raise LegalError('invalid_scenarios')
                if check(branch[key]):raise LegalError('visible_references')
            ids=branch['citations']
            if not isinstance(ids,list) or not ids or len(ids)>6 or any(not isinstance(c,str) or c not in available for c in ids):raise LegalError('invalid_citations')


class LegalPipeline:
    def __init__(self,root,model,demo=False):self.root=Path(root);self.model=model;self.demo=demo
    async def context_for_task(self,task,*,budget,as_of_date):
        if task['function_id']=='general_legal_help':
            if self.demo:return {'prompt':'Учебная демонстрация','fragments':[],'source_errors':['source_demo_unavailable'],'trace':[]}
            cache_root=Path(os.getenv('CONSULTANT_CACHE_DIR','data/consultant-cache'))
            reserved=max(0,budget.context_left-6000) if re.search(r'прод|купл',task['formulation'],re.I) else 0
            reserved_articles=max(0,budget.articles_left-4) if re.search(r'прод|купл',task['formulation'],re.I) else 0
            budget.context_left-=reserved;budget.articles_left-=reserved_articles
            try:return await ConsultantLegalMCP(self.root,cache_root).context(search_query(task['formulation'],task['legal_topic']),legal_topic=task['legal_topic'],as_of_date=as_of_date,budget=budget)
            finally:budget.context_left+=reserved;budget.articles_left+=reserved_articles
        if as_of_date!=datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat():raise SourceError('source_edition_unknown')
        context=await LocalLegalMCP(self.root,demo=self.demo).context(task['formulation'])
        chosen=[];task_remaining=min(6000,budget.context_left) if re.search(r'прод|купл',task['formulation'],re.I) else budget.context_left
        for fragment in context['fragments']:
            if len(fragment['text'])<=task_remaining:chosen.append(fragment);budget.context_left-=len(fragment['text']);task_remaining-=len(fragment['text'])
        if len(chosen)!=len(context['fragments']):context['limitations']=[*context.get('limitations',[]),'Часть норм не вошла в первоначальный контекст; ответ ограничивается прочитанными фрагментами.']
        if not chosen and context['fragments']:raise SourceError('source_budget_exhausted')
        context['fragments']=chosen;return context
    async def fallback_context(self,task,*,budget,as_of_date):
        empty={'prompt':'','fragments':[],'trace':['public.fallback'],'limitations':[]}
        if self.demo or budget.rate_limited or time.monotonic()>budget.deadline-15:return empty
        topic=task['legal_topic']
        if not re.search(r'прод|купл|сделк|оформлен',task['formulation'],re.I):return empty
        if topic not in ('land','tax','civil'):return empty
        if topic=='civil' and task['function_id']=='general_legal_help':return empty
        if topic=='land':topic='civil'
        try:
            context=await ConsultantLegalMCP(self.root,Path(os.getenv('CONSULTANT_CACHE_DIR','data/consultant-cache'))).context(search_query(task['formulation'],topic),legal_topic=topic,as_of_date=as_of_date,budget=budget,fallback=True)
            context['trace'].append('public.fallback');return context
        except Exception as exc:
            logging.getLogger(__name__).warning('public_fallback_failed code=%s',getattr(exc,'code','source_unavailable'))
            return {**empty,'source_errors':[getattr(exc,'code','source_unavailable')]}
    @staticmethod
    def merge_context(primary,extra):
        dates=[c['source_checked_at'] for c in (primary,extra) if c.get('source_checked_at')]
        return {**primary,'fragments':primary['fragments']+extra['fragments'],'trace':extra.get('trace',[]),'limitations':primary.get('limitations',[])+extra.get('limitations',[]),'source_checked_at':min(dates) if dates else None}
    async def run(self,question,intake,history=None):
        started=time.monotonic();stage='input';run_id=uuid.uuid4().hex;trace=['input.validate']
        base={'status':'error','question':question if isinstance(question,str) else '', 'tasks':[], 'missing_fields':[], 'answer':'','sources':[], 'mode':'demo' if self.demo else 'live','trace':trace,'limitations':[], 'diagnostics':{'run_id':run_id}}
        answers=[];bases=[];sources={};limits=[];questions={};outcomes=[];checked=[];partial=False;unanswered=False;errors=[]
        def finish():
            return {**base,'status':'partial_answer' if partial or unanswered else 'answered','answer':'\n\n'.join(answers),'sources':list(sources.values()),'legal_bases':bases,'missing_fields':list(questions.values())[:3],'limitations':list(dict.fromkeys(limits)),'task_outcomes':outcomes,'source_checked_at':min(checked) if checked else None}
        def diagnostic(exc):
            code=getattr(exc,'code','pipeline_timeout' if isinstance(exc,TimeoutError) else 'mcp_failure' if stage=='mcp_context' else 'invalid_plan' if stage in ('classify','plan_validate') else 'internal_error')
            data={'run_id':run_id,'stage':stage,'code':code,'elapsed_seconds':round(time.monotonic()-started,2)}
            if getattr(exc,'http_status',None):data['http_status']=exc.http_status
            logging.getLogger(__name__).warning('legal_failure run=%s stage=%s code=%s elapsed=%s',run_id,stage,code,data['elapsed_seconds']);return data
        try:
            valid_input(question,intake);history=[] if history is None else history
            if not isinstance(history,list) or len(history)>200:raise ValueError('История превышает 200 сообщений. Начните новый чат.')
            for message in history:
                if not isinstance(message,dict) or set(message)-{'text','intake'}:raise ValueError('Некорректная история чата.')
                valid_input(message.get('text'),message.get('intake',{}))
            if sum(len(m['text'])+sum(map(len,m.get('intake',{}).values())) for m in history)>100000:raise ValueError('История слишком велика. Начните новый чат; переписка останется доступной.')
        except ValueError as exc:return {**base,'status':'invalid_request','answer':str(exc)}
        try:
            async with asyncio.timeout(120):
                budget=RequestBudget(deadline=started+120);stage='classify'
                plan=await self.model.classify(question,intake,**({'history':history} if history else {}));stage='plan_validate'
                known=plan.get('known_fields',{}) if isinstance(plan,dict) else {};valid_input(question,known);intake={**known,**intake}
                trace+=['llm.classify','plan.validate'];tasks=validate_plan(plan);base['tasks']=tasks
                if not tasks:
                    if plan.get('needs_clarification'):return {**base,'status':'needs_clarification','answer':'Уточните, относится ли вопрос к праву РФ: право других стран пока не подключено.' if plan.get('clarification_reason')=='jurisdiction' else 'Опишите юридическую задачу подробнее и укажите желаемый результат.','missing_fields':[{'key':k,'label':FIELD_LABELS[k]} for k in (('jurisdiction',) if plan.get('clarification_reason')=='jurisdiction' else GENERAL) if not intake.get(k)]}
                    return {**base,'status':'unsupported','answer':'Этот запрос не относится к поддерживаемой юридической помощи по праву РФ. Уточните правовую задачу и страну.'}
                for task in tasks:
                    try:
                        if time.monotonic()>=budget.deadline-2:raise SourceError('source_budget_exhausted')
                        stage='mcp_context';as_of_date=task.get('as_of_date',datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat())
                        fallback_used=False
                        try:context=await self.context_for_task(task,budget=budget,as_of_date=as_of_date)
                        except SourceError as exc:
                            context={'prompt':'','fragments':[],'trace':[],'source_errors':[exc.code]}
                        trace.extend(context['trace']);fragments=context['fragments']
                        if not fragments:
                            fallback_used=True;extra=await self.fallback_context(task,budget=budget,as_of_date=as_of_date)
                            if extra['fragments']:context={**extra,'prompt':extra.get('prompt') or context['prompt']};fragments=context['fragments'];trace.extend(extra.get('trace',[]))
                            elif extra.get('source_errors'):context['source_errors']=context.get('source_errors',[])+extra['source_errors']
                        if not fragments:
                            source_errors=context.get('source_errors',[])
                            if any(c not in ('search_no_candidates','source_demo_unavailable') for c in source_errors):raise SourceError(source_errors[0])
                            unanswered=True;outcomes.append({'task_id':task['task_id'],'status':'insufficient_sources','summary':task['formulation'][:200]+': недостаточно нормативных материалов.'});continue
                        if not self.demo and any(f.get('demo',True) for f in fragments):raise SourceError('source_demo_rejected')
                        stage='answer';arguments=dict(original_question=question,formulation=task['formulation'],intake=intake,prompt=context['prompt'],fragments=fragments,scope=task['scope'])
                        if history:arguments['history']=history
                        result=await self.model.answer(**arguments);trace+=['llm.answer'];stage='answer_validate'
                        if isinstance(result,dict) and result.get('status') in ('insufficient_sources','partial_answer') and not fallback_used:
                            fallback_used=True;extra=await self.fallback_context(task,budget=budget,as_of_date=as_of_date)
                            if extra['fragments']:
                                primary_context=context;primary_result=result;primary_arguments=dict(arguments);primary_valid=False
                                try:validate_answer(primary_result,fragments,scope=task['scope']);primary_valid=True
                                except LegalError:pass
                                context=self.merge_context(context,extra);fragments=context['fragments'];arguments['fragments']=fragments;trace.extend(extra.get('trace',[]));stage='answer_fallback'
                                try:result=await self.model.answer(**arguments)
                                except Exception:
                                    if not primary_valid:raise
                                    result=primary_result;context={**primary_context,'limitations':primary_context.get('limitations',[])+['Дополнительная проверка не завершена; сохранён первоначальный проверенный разбор.']};fragments=context['fragments'];arguments=primary_arguments
                                trace.append('llm.answer_fallback');stage='answer_validate'
                        trace.append('answer.validate')
                        try:validate_answer(result,fragments,scope=task['scope'])
                        except LegalError as exc:
                            if exc.code!='visible_references' or not callable(getattr(self.model,'rewrite_answer',None)):raise
                            stage='rewrite';trace.append('llm.rewrite');result=await self.model.rewrite_answer(draft=result,**arguments);stage='rewrite_validate';validate_answer(result,fragments,scope=task['scope'])
                        if result.get('status')=='insufficient_sources':
                            base['diagnostics'].update(code='insufficient_context',stage=stage);unanswered=True;outcomes.append({'task_id':task['task_id'],'status':'insufficient_sources','summary':task['formulation'][:200]+': прочитанных материалов недостаточно.'});continue
                        if getattr(self.model,'require_legal_bases',False) and not result.get('legal_bases'):raise LegalError('invalid_legal_bases')
                        # Only now commit a task's checked result. Failed later tasks cannot erase it.
                        text=result['answer'];citations=list(result['citations']);is_partial=result.get('status')=='partial_answer'
                        if is_partial:
                            partial=True;text='Предварительный разбор: факты и документы не проверялись.\n\n'+text+'\n\nВозможные варианты:'
                            for branch in result['scenarios']:text+='\n• Если '+branch['condition'].strip()+', то '+branch['outcome'].strip();citations.extend(branch['citations'])
                            for key in result.get('missing_fields',[]):
                                if key not in ('situation','goal') and key in allowed_fields(task['legal_topic']) and not intake.get(key,'').strip():questions[key]={'key':key,'label':FIELD_LABELS[key]}
                        available={f['id']:f for f in fragments}
                        for b in result.get('legal_bases',[]):
                            f=available[b['fragment_id']];title=f['title'].split(' — часть')[0];title=(f.get('act_designation','')+' «'+title+'»') if f.get('act_designation') else title
                            item={'title':title,'article':f.get('citation',''),'explanation':b['explanation']}
                            if item not in bases:bases.append(item)
                        for c in citations:sources[c]={k:v for k,v in available[c].items() if k!='text'}
                        answers.append(text);limits.extend(context.get('limitations',[]));limits.extend(result.get('limitations',[]));outcomes.append({'task_id':task['task_id'],'status':'partial_answer' if is_partial else 'answered','summary':task['formulation'][:200]})
                        if context.get('source_checked_at'):checked.append(context['source_checked_at'])
                    except asyncio.CancelledError:raise
                    except Exception as exc:
                        data=diagnostic(exc);errors.append(data);base['diagnostics']=data;unanswered=True;outcomes.append({'task_id':task['task_id'],'status':'error','summary':task['formulation'][:200]+': доступ к материалам или проверка ответа завершились ошибкой.'})
                if answers:
                    if unanswered:limits.append('Часть запроса не разобрана; см. состояние отдельных задач.')
                    return finish()
                if not errors:return {**base,'status':'insufficient_sources','answer':'В доступных нормативных материалах недостаточно оснований для ответа. Дополнительные сведения клиента сами по себе не заменят недостающие нормы.','task_outcomes':outcomes}
        except asyncio.CancelledError:raise
        except Exception as exc:
            data=diagnostic(exc);errors.append(data);base['diagnostics']=data
            completed={item['task_id'] for item in outcomes}
            for pending in base['tasks']:
                if pending['task_id'] not in completed:outcomes.append({'task_id':pending['task_id'],'status':'error','summary':pending['formulation'][:200]+': не обработано из-за ограничения времени или сбоя.'})
            if answers:
                unanswered=True;limits.append('Остальная часть запроса не обработана из-за ограничения времени или сбоя.');return finish()
        code=errors[-1]['code'] if errors else 'internal_error'
        message='Не удалось подготовить проверенный ответ. Попробуйте повторить запрос позже.'
        if code in ('llm_timeout','pipeline_timeout'):message='Модель не успела подготовить ответ. Попробуйте повторить запрос позже.'
        elif code in ('llm_connection','llm_rate_limit','llm_http'):message='Сервис подготовки ответа временно недоступен. Попробуйте позже.'
        elif code=='source_edition_unknown':message='Не удалось подтвердить применимую редакцию нормы на нужную дату. Ответ по непроверенной редакции не подготовлен.'
        elif code.startswith('source_'):message='Нужные нормативные материалы сейчас недоступны для проверки. Это не означает отсутствия правового регулирования. Попробуйте позже.'
        return {**base,'status':'error','answer':message,'task_outcomes':outcomes}
