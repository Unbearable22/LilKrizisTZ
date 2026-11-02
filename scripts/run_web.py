"""One-command local web launcher. No shell evaluation of secrets or .env."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import venv
import webbrowser

ROOT = Path(__file__).resolve().parents[1]

def venv_python(root, windows=None):
    windows = os.name == 'nt' if windows is None else windows
    return root / ('Scripts/python.exe' if windows else 'bin/python')

def load_env(path):
    if not path.exists():
        return
    for number, line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:]
        key, sep, value = line.partition('=')
        key, value = key.strip(), value.strip()
        if not sep or not key or not key.replace('_', 'a').isalnum() or key[0].isdigit():
            raise ValueError(f'Invalid .env entry on line {number}.')
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f'Unclosed quote in .env on line {number}.')
            value = value[1:-1]
        os.environ.setdefault(key, value)

def prepare_environment(speech):
    env = ROOT / '.venv-web'
    python = venv_python(env)
    if not python.exists():
        print('Creating local Python environment...', flush=True)
        venv.EnvBuilder(with_pip=True).create(env)
    requirements = [ROOT / 'requirements-legal.txt']
    if speech:
        requirements.append(ROOT / 'requirements-speech.txt')
    digest = hashlib.sha256(b''.join(p.read_bytes() for p in requirements)).hexdigest()
    marker = env / '.web-requirements.sha256'
    if not marker.exists() or marker.read_text() != digest:
        print('Installing dependencies (first start or updated requirements)...', flush=True)
        command = [str(python), '-m', 'pip', 'install']
        for path in requirements:
            command.extend(['-r', str(path)])
        subprocess.run(command, check=True, cwd=ROOT)
        marker.write_text(digest)
    return python

def app_running(url):
    try:
        with urllib.request.urlopen(url + '/api/legal-help/config', timeout=1) as response:
            return json.load(response).get('mode') in ('live', 'demo')
    except Exception:
        return False

def port_occupied(port):
    with socket.socket() as probe:
        return probe.connect_ex(('127.0.0.1', port)) == 0

def choose_endpoint(port, auto=False):
    for candidate in range(port, min(port + (20 if auto else 1), 65536)):
        if not port_occupied(candidate):
            return candidate, False
        if app_running(f'http://127.0.0.1:{candidate}'):
            return candidate, True
    raise ValueError(f'No available web port starting from {port}. Close another application or choose --port.')

def main(argv=None):
    parser = argparse.ArgumentParser(description='Start GROUNDandLAW web chat and open the browser.')
    parser.add_argument('--check-config', action='store_true', help='Check required settings without starting the server.')
    parser.add_argument('--demo', action='store_true', help='Run without LLM API calls.')
    parser.add_argument('--no-speech', action='store_true', help='Skip local Whisper installation.')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--auto-port', action='store_true', help='Choose another port automatically when busy.')
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        raise ValueError('Port must be between 1 and 65535.')
    os.chdir(ROOT)
    load_env(ROOT / '.env')
    missing=[k for k in ('LLM_URL', 'LLM_API_KEY', 'LLM_MODEL') if not os.environ.get(k, '').strip()]
    if not args.demo and missing:
        if not (ROOT / '.env').exists():
            (ROOT / '.env').write_bytes((ROOT / '.env.example').read_bytes())
        message='Missing settings: '+', '.join(missing)+'. File: '+str(ROOT / '.env')
        if args.check_config:
            print(message)
            return 1
        raise ValueError(message)
    if args.check_config:
        print('Model settings are configured.')
        return 0
    args.port, running = choose_endpoint(args.port, args.auto_port)
    url = f'http://127.0.0.1:{args.port}'
    if running:
        print(f'Web chat is already running: {url}')
        if not args.no_browser:
            webbrowser.open(url)
        return 0
    if not (3, 10) <= sys.version_info[:2] <= (3, 13):
        raise ValueError('Install Python 3.12 (recommended) or 3.13 for the Windows launcher and local Whisper.')
    python = prepare_environment(not args.no_speech)
    if not args.no_speech:
        model = ROOT / 'data/speech-model'
        if not all((model / name).exists() for name in ('model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt')):
            print('Downloading local Whisper model (about 462 MiB, first start only)...', flush=True)
            subprocess.run([str(python), '-c', "from huggingface_hub import snapshot_download; import sys; snapshot_download('Systran/faster-whisper-small', local_dir=sys.argv[1], allow_patterns=['model.bin','config.json','tokenizer.json','vocabulary.txt'])", str(model)], check=True, cwd=ROOT)
        os.environ['SPEECH_PYTHON'] = str(python)
    command = [str(python), '-m', 'land_assistant', 'web', '--port', str(args.port)]
    if args.demo:
        command.append('--demo')
    print(f'Starting {url}. Keep this window open; Ctrl+C stops the server.', flush=True)
    child = subprocess.Popen(command, cwd=ROOT)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if child.poll() is not None:
                return child.returncode or 1
            if app_running(url):
                print(f'Ready: {url}', flush=True)
                if not args.no_browser:
                    webbrowser.open(url)
                return child.wait()
            time.sleep(.25)
        raise ValueError('Web server did not become ready within 30 seconds. See messages above.')
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('\nWeb chat stopped.')
        raise SystemExit(0)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        # Do not print environment values or provider credentials.
        print(f'Startup failed: {exc}', file=sys.stderr)
        raise SystemExit(1)
