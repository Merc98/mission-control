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
import tomllib

HOME = Path.home()
APP_HOME = Path(os.environ.get('AGENTFORGE_HOME', str(HOME / '.agentforge')))
DEFAULT_BRIDGE = Path(os.environ.get('CLI_BRIDGE_HOME', str(APP_HOME / 'bridge')))
DEFAULT_DB = APP_HOME / 'mission_control.db'
DEFAULT_CONFIG = APP_HOME / 'config.toml'
WEB_ROOT = Path(__file__).parent / 'web'
CATALOG_PATH = Path(__file__).parent / 'data' / 'agent_catalog.json'

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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS components (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source TEXT NOT NULL,
            target_scope TEXT NOT NULL,
            target_id TEXT NOT NULL,
            install_path TEXT NOT NULL,
            status TEXT NOT NULL,
            created_ts INTEGER NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_configs (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_ts INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def ensure_config(path: Path, bridge_path: Path):
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(24)
    body = (
        '# AgentForge local configuration\n'
        f'auth_token = "{token}"\n'
        f'bridge_path = "{bridge_path}"\n'
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
    finally:
        server.server_close()


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


def load_mcp_sources(config_path: Path):
    raw = config_path.read_text(encoding='utf-8')
    parsed = tomllib.loads(raw)
    sources = parsed.get('mcp_sources', [])
    if not isinstance(sources, list):
        raise ValueError('mcp_sources must be a TOML array')
    normalized = []
    for i, src in enumerate(sources):
        if not isinstance(src, str):
            raise ValueError(f'mcp_sources[{i}] must be a string')
        normalized.append(src)
    return normalized


def load_catalog(catalog_path: Path = CATALOG_PATH):
    if not catalog_path.exists():
        return []
    return json.loads(catalog_path.read_text(encoding='utf-8'))


def find_catalog_entry(entry_id: str):
    for entry in load_catalog():
        if entry.get('id') == entry_id:
            return entry
    return None


def install_catalog_entry(entry: dict, install_root: Path, target_scope: str, target_id: str):
    install_root.mkdir(parents=True, exist_ok=True)
    entry_id = entry['id']
    kind = entry.get('kind', 'agent')
    source_type = entry.get('source_type', 'builtin')
    source = entry.get('source', '')
    install_path = install_root / entry_id
    status = 'installed'

    if source_type == 'github':
        if install_path.exists():
            status = 'already_present'
        else:
            rc = subprocess.run(
                ['git', 'clone', '--depth', '1', source, str(install_path)],
                check=False,
            ).returncode
            if rc != 0:
                status = f'clone_failed_rc_{rc}'
    else:
        install_path.mkdir(parents=True, exist_ok=True)
        manifest = install_path / 'manifest.json'
        manifest.write_text(json.dumps(entry, indent=2), encoding='utf-8')

    return {
        'id': entry_id,
        'kind': kind,
        'name': entry.get('name', entry_id),
        'source_type': source_type,
        'source': source,
        'target_scope': target_scope,
        'target_id': target_id,
        'install_path': str(install_path),
        'status': status,
    }


def record_component_install(db_path: Path, installed: dict):
    conn = ensure_db(db_path)
    conn.execute(
        """
        INSERT OR REPLACE INTO components
        (id, kind, name, source_type, source, target_scope, target_id, install_path, status, created_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            installed['id'],
            installed['kind'],
            installed['name'],
            installed['source_type'],
            installed['source'],
            installed['target_scope'],
            installed['target_id'],
            installed['install_path'],
            installed['status'],
            int(time.time()),
        ),
    )
    conn.commit()
    conn.close()


def list_components(db_path: Path, kind_filter: str | None = None):
    conn = ensure_db(db_path)
    cur = conn.cursor()
    if kind_filter:
        rows = cur.execute(
            'SELECT id, kind, name, source, target_scope, target_id, install_path, status FROM components WHERE kind = ? ORDER BY id',
            (kind_filter,),
        ).fetchall()
    else:
        rows = cur.execute(
            'SELECT id, kind, name, source, target_scope, target_id, install_path, status FROM components ORDER BY kind, id'
        ).fetchall()
    conn.close()
    return [
        {
            'id': r[0],
            'kind': r[1],
            'name': r[2],
            'source': r[3],
            'target_scope': r[4],
            'target_id': r[5],
            'install_path': r[6],
            'status': r[7],
        }
        for r in rows
    ]


def set_agent_config(db_path: Path, agent_id: str, key: str, value: str):
    conn = ensure_db(db_path)
    row_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO agent_configs (id, agent_id, key, value, updated_ts)
        VALUES (?, ?, ?, ?, ?)
        """,
        (row_id, agent_id, key, value, int(time.time())),
    )
    conn.commit()
    conn.close()
    return {'id': row_id, 'agent_id': agent_id, 'key': key, 'value': value}


def parse_target(target: str):
    if target == 'global':
        return 'global', 'global'
    if target.startswith('agent:'):
        return 'agent', target.split(':', 1)[1]
    raise ValueError("target must be 'global' or 'agent:<agent_id>'")


def run_debug_checks(bridge: Path, db: Path, config: Path):
    checks = []

    try:
        ensure_app_dirs(bridge)
        checks.append({'check': 'bridge_dirs', 'ok': True, 'path': str(bridge)})
    except Exception as exc:
        checks.append({'check': 'bridge_dirs', 'ok': False, 'error': str(exc)})

    try:
        conn = ensure_db(db)
        conn.close()
        checks.append({'check': 'sqlite_ready', 'ok': True, 'path': str(db)})
    except Exception as exc:
        checks.append({'check': 'sqlite_ready', 'ok': False, 'error': str(exc)})

    try:
        ensure_config(config, bridge)
        checks.append({'check': 'config_ready', 'ok': True, 'path': str(config)})
    except Exception as exc:
        checks.append({'check': 'config_ready', 'ok': False, 'error': str(exc)})

    model_discovery = discover_model_endpoints()
    checks.append({'check': 'model_endpoints', 'ok': True, 'details': model_discovery})

    cli = detect_cli_agents()
    checks.append({'check': 'cli_agents', 'ok': True, 'details': cli})
    checks.append({'check': 'catalog_items', 'ok': True, 'count': len(load_catalog())})

    recommendations = []
    if not any(v.get('installed') for v in cli.values()):
        recommendations.append('No CLI agents found in PATH. Run: agentforge install all')
    if not model_discovery['ollama']['ok']:
        recommendations.append('Ollama endpoint not reachable at http://127.0.0.1:11434/api/tags')
    if not model_discovery['lm_studio']['ok']:
        recommendations.append('LM Studio endpoint not reachable at http://127.0.0.1:1234/v1/models')
    recommendations.append('Use catalog list/install to manage Skill vs Plugin vs MCP separately.')
    if not recommendations:
        recommendations.append('Core local checks passed. Next step: connect real-time WS + whiteboard persistence.')

    return {'checks': checks, 'recommendations': recommendations}


def main():
    ap = argparse.ArgumentParser(prog='agentforge', description='AgentForge Mission Control CLI')
    ap.add_argument('--bridge', default=str(DEFAULT_BRIDGE), help='Bridge folder path')
    ap.add_argument('--db', default=str(DEFAULT_DB), help='SQLite DB path')
    ap.add_argument('--config', default=str(DEFAULT_CONFIG), help='Config TOML path')
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
    p_mcp_load.add_argument('--config', default=None)

    sub.add_parser('config', help='Initialize/show local config')
    sub.add_parser('debug', help='Run local diagnostics and recommendations')

    sub.add_parser('status', help='Show bridge summary')

    p_cancel = sub.add_parser('cancel', help='Cancel operations')
    p_cancel.add_argument('--target', default='')

    p_catalog = sub.add_parser('catalog', help='Browse/install catalog entries (agents/skills/plugins/mcp)')
    catalog_sub = p_catalog.add_subparsers(dest='catalog_cmd', required=True)
    p_catalog_list = catalog_sub.add_parser('list', help='List catalog entries')
    p_catalog_list.add_argument('--kind', choices=['agent', 'skill', 'plugin', 'mcp'], default='')
    p_catalog_list.add_argument('--category', default='')
    p_catalog_list.add_argument('--q', default='')
    p_catalog_install = catalog_sub.add_parser('install', help='Install catalog entry')
    p_catalog_install.add_argument('entry_id')
    p_catalog_install.add_argument('--target', default='global', help='global | agent:<agent_id>')
    p_catalog_install.add_argument('--path', default=str(APP_HOME / 'packages'))

    p_component = sub.add_parser('component', help='Installed components and boundaries')
    component_sub = p_component.add_subparsers(dest='component_cmd', required=True)
    p_component_list = component_sub.add_parser('list', help='List installed components')
    p_component_list.add_argument('--kind', choices=['agent', 'skill', 'plugin', 'mcp'], default='')

    p_agent = sub.add_parser('agent', help='Agent-level configuration')
    agent_sub = p_agent.add_subparsers(dest='agent_cmd', required=True)
    p_agent_cfg = agent_sub.add_parser('config-set', help='Set config key/value for an agent')
    p_agent_cfg.add_argument('--agent-id', required=True)
    p_agent_cfg.add_argument('--key', required=True)
    p_agent_cfg.add_argument('--value', required=True)

    args = ap.parse_args()
    bridge = Path(args.bridge)
    db = Path(args.db)
    config = Path(args.config) if args.config is not None else DEFAULT_CONFIG

    if args.cmd == 'start':
        ensure_config(config, bridge)
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
        cfg = Path(args.config) if args.config is not None else config
        ensure_config(cfg, bridge)
        sources = load_mcp_sources(cfg)
        print(json.dumps({'config': str(cfg), 'status': 'loaded', 'sources': sources}, indent=2))
        return

    if args.cmd == 'config':
        cfg = ensure_config(config, bridge)
        print(json.dumps({'config': str(cfg), 'exists': cfg.exists()}, indent=2))
        return

    if args.cmd == 'debug':
        print(json.dumps(run_debug_checks(bridge, db, config), indent=2))
        return

    if args.cmd == 'catalog' and args.catalog_cmd == 'list':
        items = load_catalog()
        if args.kind:
            items = [x for x in items if x.get('kind') == args.kind]
        if args.category:
            items = [x for x in items if x.get('category') == args.category]
        if args.q:
            needle = args.q.lower()
            items = [
                x
                for x in items
                if needle in x.get('name', '').lower()
                or needle in x.get('id', '').lower()
                or any(needle in t.lower() for t in x.get('tags', []))
            ]
        print(json.dumps({'count': len(items), 'items': items}, indent=2))
        return

    if args.cmd == 'catalog' and args.catalog_cmd == 'install':
        entry = find_catalog_entry(args.entry_id)
        if not entry:
            raise SystemExit(f'Catalog entry not found: {args.entry_id}')
        target_scope, target_id = parse_target(args.target)
        installed = install_catalog_entry(entry, Path(args.path), target_scope, target_id)
        record_component_install(db, installed)
        print(json.dumps({'installed': installed}, indent=2))
        return

    if args.cmd == 'component' and args.component_cmd == 'list':
        kind = args.kind or None
        print(json.dumps({'items': list_components(db, kind)}, indent=2))
        return

    if args.cmd == 'agent' and args.agent_cmd == 'config-set':
        result = set_agent_config(db, args.agent_id, args.key, args.value)
        print(json.dumps({'updated': result}, indent=2))
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
