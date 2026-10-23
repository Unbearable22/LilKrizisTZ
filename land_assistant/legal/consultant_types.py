"""Shared source contracts; no client identity or model credentials."""
from dataclasses import dataclass,field,asdict
import time
from .errors import LegalError

class SourceError(LegalError):
    pass

@dataclass
class RequestBudget:
    deadline:float=field(default_factory=lambda:time.monotonic()+120)
    roots_left:int=3
    articles_left:int=8
    context_left:int=20000
    network_seconds_left:float=25
    rate_limited:bool=False
    def require(self):
        if self.rate_limited:raise SourceError('source_rate_limit')
        if time.monotonic()>=self.deadline or self.network_seconds_left<=0:raise SourceError('source_budget_exhausted')
    def take(self,kind):
        self.require();key='roots_left' if kind=='root' else 'articles_left'
        if getattr(self,key)<=0:raise SourceError('source_budget_exhausted')
        setattr(self,key,getattr(self,key)-1)
    def wire(self):return asdict(self)

@dataclass
class DocumentPage:
    canonical_url:str
    status:int
    headers:dict
    body:str
    checked_at:str
