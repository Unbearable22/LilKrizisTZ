import os
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Settings:
    data_dir: Path
    telegram_token: str = ''
    allowed_users: tuple[int, ...] = ()
    admin_token: str = ''
    llm_url: str = ''
    llm_key: str = ''
    llm_model: str = ''
    nspd_url: str = ''
    nspd_key: str = ''
    image_url: str = ''
    image_key: str = ''
    image_model: str = ''
    monitor_seconds: int = 3600

    llm_classify_timeout: float = 45
    llm_answer_timeout: float = 60
    llm_classifier_model: str = ''
    llm_answer_tokens: int = 6144
    consultant_cache_dir: Path = Path("data/consultant-cache")

    @classmethod
    def from_env(cls):
        return cls(Path(os.getenv('DATA_DIR', 'data')),
                   os.getenv('TELEGRAM_BOT_TOKEN', ''),
                   tuple(int(x.strip()) for x in os.getenv('ALLOWED_TELEGRAM_IDS', '').split(',') if x.strip()),
                   os.getenv('ADMIN_API_TOKEN', ''),
                   os.getenv('LLM_URL', ''), os.getenv('LLM_API_KEY', ''), os.getenv('LLM_MODEL', ''),
                   os.getenv('NSPD_ADAPTER_URL', ''), os.getenv('NSPD_API_KEY', ''),
                   os.getenv('IMAGE_API_URL', ''), os.getenv('IMAGE_API_KEY', ''), os.getenv('IMAGE_MODEL', ''),
                   max(60, int(os.getenv('MONITOR_SECONDS', '3600'))),
                   min(90,max(5,float(os.getenv('LLM_CLASSIFY_TIMEOUT','45')))),
                   min(90,max(5,float(os.getenv('LLM_ANSWER_TIMEOUT','60')))),
                   os.getenv('LLM_CLASSIFIER_MODEL',''),
                   min(12000,max(1024,int(os.getenv('LLM_ANSWER_TOKENS','6144')))),
                   Path(os.getenv('CONSULTANT_CACHE_DIR','data/consultant-cache')))
