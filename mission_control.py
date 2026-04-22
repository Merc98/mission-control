#!/usr/bin/env python3
import argparse
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import time
import uuid
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

HOME = Path.home()
APP_HOME = Path(os.environ.get('AGENTFORGE_HOME', str(HOME / '.agentforge')))
DEFAULT_BRIDGE = Path(os.environ.get('CLI_BRIDGE_HOME', str(APP_HOME / 'bridge')))
DEFAULT_DB = APP_HOME / 'mission_control.db'
DEFAULT_CONFIG = APP_HOME / 'config.toml'
WEB_ROOT = Path(__file__).parent / 'web'

AGENTS = {
    'codex': ['codex'],
    'gemini': ['gemini'],
    'qwen': ['qwen'],
}


def ensure_app_dirs(bridge: Path):
    APP_HOME.mkdir(parents=True, exist_ok=True)
    for d in ['inbox', 'outbox', 'state']:
        (bridge / d).mkdir(parents=True, exist_ok=True)


def ensure_db(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS missions (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            objective TEXT NOT NULL,
            status TEXT NOT NULL,
            created_ts INTEGER NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS teams (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            mission_id TEXT,
            members_json TEXT NOT NULL,
            created_ts INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def ensure_config(path: Path):
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(24)
    body = (
        '# AgentForge local configuration\n'
        f'auth_token = "{token}"\n'
        f'bridge_path = "{DEFAULT_BRIDGE}"\n'
        'mcp_sources = []\n'
    )
    path.write_text(body, encoding='utf-8')
    return path


def detect_cli_agents():
    found = {}
    for name, bins in AGENTS.items():
        exe = None
        for candidate in bins:
            resolved = shutil.which(candidate)
            if resolved:
                exe = resolved
                break
        found[name] = {'installed': bool(exe), 'bin': exe or ''}
    return found


def query_json(url: str, timeout: float = 1.5):
    with urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def discover_model_endpoints():
    out = {'ollama': {'ok': False, 'models': []}, 'lm_studio': {'ok': False, 'models': []}}

    try:
        data = query_json('http://127.0.0.1:11434/api/tags')
        out['ollama'] = {
            'ok': True,
            'models': [m.get('name', 'unknown') for m in data.get('models', [])],
        }
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        pass

    try:
        data = query_json('http://127.0.0.1:1234/v1/models')
        out['lm_studio'] = {
            'ok': True,
            'models': [m.get('id', 'unknown') for m in data.get('data', [])],
        }
    except (URLError, TimeoutError, OSError, json.JSONDecodeError):
        pass

    return out


def install_agent(name: str):
    pkg = {
        'codex': '@openai/codex',
        'gemini': '@google/gemini-cli',
        'qwen': '@qwen-code/qwen-code',
    }.get(name)
    if not pkg:
        raise SystemExit(f'Unknown agent: {name}')
    return subprocess.run(['npm', 'i', '-g', pkg], check=False).returncode


def write_msg(bridge: Path, to: str, body: str, msg_type='task', sender='agentforge-cli'):
    ensure_app_dirs(bridge)
    ts = int(time.time())
    mid = str(uuid.uuid4())
    payload = {
        'id': mid,
        'from': sender,
        'to': to,
        'ts': str(ts),
        'type': msg_type,
        'body': body,
        'status': 'queued',
    }
    f = bridge / 'inbox' / f'msg-{ts}-{sender}-{to}-{mid}.json'
    f.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return f


def read_json_files(path: Path):
    out = []
    for p in sorted(path.glob('*.json'))[-50:]:
        try:
            out.append(json.loads(p.read_text(encoding='utf-8')))
        except Exception:
            out.append({'file': p.name, 'error': 'invalid_json'})
    return out


def launch_ui(host: str, port: int, open_browser: bool):
    WEB_ROOT.mkdir(exist_ok=True)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    server = ThreadingHTTPServer((host, port), Handler)
    url = f'http://{host}:{port}'
    if open_browser:
        webbrowser.open(url)
    print(json.dumps({'status': 'running', 'url': url}, indent=2))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def create_mission(db_path: Path, name: str, objective: str):
    conn = ensure_db(db_path)
    mid = str(uuid.uuid4())
    ts = int(time.time())
    conn.execute(
        'INSERT INTO missions (id, name, objective, status, created_ts) VALUES (?, ?, ?, ?, ?)',
        (mid, name, objective, 'active', ts),
    )
    conn.commit()
    conn.close()
    return {'id': mid, 'name': name, 'objective': objective, 'status': 'active'}


def create_team(db_path: Path, name: str, mission_id: str, members: list[str]):
    conn = ensure_db(db_path)
    tid = str(uuid.uuid4())
    ts = int(time.time())
    conn.execute(
        'INSERT INTO teams (id, name, mission_id, members_json, created_ts) VALUES (?, ?, ?, ?, ?)',
        (tid, name, mission_id or None, json.dumps(members), ts),
    )
    conn.commit()
    conn.close()
    return {'id': tid, 'name': name, 'mission_id': mission_id, 'members': members}


def status(bridge: Path):
    ensure_app_dirs(bridge)
    data = {
        'bridge': str(bridge),
        'counts': {
            'inbox': len(list((bridge / 'inbox').glob('*.json'))),
            'outbox': len(list((bridge / 'outbox').glob('*.json'))),
            'state': len(list((bridge / 'state').glob('*.json'))),
        },
        'state': read_json_files(bridge / 'state'),
    }
    return data


def main():
    ap = argparse.ArgumentParser(prog='agentforge', description='AgentForge Mission Control CLI')
    ap.add_argument('--bridge', default=str(DEFAULT_BRIDGE), help='Bridge folder path')
    ap.add_argument('--db', default=str(DEFAULT_DB), help='SQLite DB path')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p_start = sub.add_parser('start', help='Start local dashboard server')
    p_start.add_argument('--host', default='127.0.0.1')
    p_start.add_argument('--port', type=int, default=8765)
    p_start.add_argument('--no-open', action='store_true', help='Do not open browser automatically')

    p_agents = sub.add_parser('agents', help='Agent operations')
    agents_sub = p_agents.add_subparsers(dest='agents_cmd', required=True)
    agents_sub.add_parser('list', help='List discovered agents/models')

    p_install = sub.add_parser('install', help='Install one or all CLI agents')
    p_install.add_argument('agent', choices=['codex', 'gemini', 'qwen', 'all'])

    p_dispatch = sub.add_parser('dispatch', help='Send instruction to one/all agents')
    p_dispatch.add_argument('to', choices=['codex', 'gemini', 'qwen', 'all'])
    p_dispatch.add_argument('body')

    p_mission = sub.add_parser('mission', help='Mission operations')
    mission_sub = p_mission.add_subparsers(dest='mission_cmd', required=True)
    p_mission_new = mission_sub.add_parser('new', help='Create a new mission')
    p_mission_new.add_argument('--name', required=True)
    p_mission_new.add_argument('--objective', required=True)

    p_team = sub.add_parser('team', help='Team operations')
    team_sub = p_team.add_subparsers(dest='team_cmd', required=True)
    p_team_create = team_sub.add_parser('create', help='Create a squad/team')
    p_team_create.add_argument('--name', required=True)
    p_team_create.add_argument('--mission-id', default='')
    p_team_create.add_argument('--members', nargs='*', default=[])

    p_termux = sub.add_parser('termux', help='Termux bridge helpers')
    termux_sub = p_termux.add_subparsers(dest='termux_cmd', required=True)
    termux_sub.add_parser('pair', help='Print pairing checklist for Android + Cloudflare Tunnel')

    p_mcp = sub.add_parser('mcp', help='MCP loader operations')
    mcp_sub = p_mcp.add_subparsers(dest='mcp_cmd', required=True)
    p_mcp_load = mcp_sub.add_parser('load', help='Load MCP sources from config.toml')
    p_mcp_load.add_argument('--config', default=str(DEFAULT_CONFIG))

    p_config = sub.add_parser('config', help='Initialize/show local config')
    p_config.add_argument('--path', default=str(DEFAULT_CONFIG))

    sub.add_parser('status', help='Show bridge summary')

    p_cancel = sub.add_parser('cancel', help='Cancel operations')
    p_cancel.add_argument('--target', default='')

    args = ap.parse_args()
    bridge = Path(args.bridge)
    db = Path(args.db)

    if args.cmd == 'start':
        ensure_config(DEFAULT_CONFIG)
        launch_ui(args.host, args.port, not args.no_open)
        return

    if args.cmd == 'agents' and args.agents_cmd == 'list':
        print(json.dumps({'cli_agents': detect_cli_agents(), 'models': discover_model_endpoints()}, indent=2))
        return

    if args.cmd == 'install':
        names = ['codex', 'gemini', 'qwen'] if args.agent == 'all' else [args.agent]
        result = {n: {'rc': install_agent(n)} for n in names}
        print(json.dumps(result, indent=2))
        return

    if args.cmd == 'dispatch':
        targets = ['codex', 'gemini', 'qwen'] if args.to == 'all' else [args.to]
        files = [str(write_msg(bridge, t, args.body)) for t in targets]
        print(json.dumps({'queued': files}, indent=2))
        return

    if args.cmd == 'mission' and args.mission_cmd == 'new':
        print(json.dumps(create_mission(db, args.name, args.objective), indent=2))
        return

    if args.cmd == 'team' and args.team_cmd == 'create':
        print(json.dumps(create_team(db, args.name, args.mission_id, args.members), indent=2))
        return

    if args.cmd == 'termux' and args.termux_cmd == 'pair':
        print(
            json.dumps(
                {
                    'steps': [
                        'Install cloudflared on Android/Termux',
                        'Run: cloudflared tunnel login',
                        'Run: cloudflared tunnel create agentforge-termux',
                        'Expose SSH: cloudflared tunnel --url ssh://localhost:8022 run agentforge-termux',
                        'Register tunnel hostname in AgentForge config',
                    ]
                },
                indent=2,
            )
        )
        return

    if args.cmd == 'mcp' and args.mcp_cmd == 'load':
        cfg = Path(args.config)
        ensure_config(cfg)
        print(json.dumps({'config': str(cfg), 'status': 'loaded_stub', 'note': 'TOML parsing wired for next iteration'}, indent=2))
        return

    if args.cmd == 'config':
        cfg = ensure_config(Path(args.path))
        print(json.dumps({'config': str(cfg), 'exists': cfg.exists()}, indent=2))
        return

    if args.cmd == 'status':
        print(json.dumps(status(bridge), indent=2))
        return

    if args.cmd == 'cancel':
        body = 'CANCEL_ALL' if not args.target else f'CANCEL:{args.target}'
        f = write_msg(bridge, 'all', body, msg_type='control')
        print(json.dumps({'cancel_msg': str(f)}, indent=2))
        return


if __name__ == '__main__':
    main()
