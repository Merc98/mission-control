#!/usr/bin/env python3
import argparse, json, os, shutil, subprocess, time, uuid
from pathlib import Path

HOME = Path.home()
DEFAULT_BRIDGE = Path(os.environ.get('CLI_BRIDGE_HOME', r'C:\Users\beloc\CLI Workspace\nfc\cli-bridge'))

AGENTS = {
    'codex': ['codex'],
    'gemini': ['gemini'],
    'qwen': ['qwen']
}


def ensure_bridge(path: Path):
    for d in ['inbox', 'outbox', 'state']:
        (path / d).mkdir(parents=True, exist_ok=True)


def detect_agents():
    found = {}
    for name, bins in AGENTS.items():
        exe = next((shutil.which(b) for b in bins if shutil.which(b)), None)
        found[name] = {'installed': bool(exe), 'bin': exe or ''}
    return found


def install_agent(name: str):
    if name == 'codex':
        cmd = ['npm', 'i', '-g', '@openai/codex']
    elif name == 'gemini':
        cmd = ['npm', 'i', '-g', '@google/gemini-cli']
    elif name == 'qwen':
        cmd = ['npm', 'i', '-g', '@qwen-code/qwen-code']
    else:
        raise SystemExit(f'Unknown agent: {name}')
    return subprocess.run(cmd, check=False).returncode


def write_msg(bridge: Path, to: str, body: str, msg_type='task', sender='agentforge-cli'):
    ensure_bridge(bridge)
    ts = int(time.time())
    mid = str(uuid.uuid4())
    payload = {
        'id': mid,
        'from': sender,
        'to': to,
        'ts': str(ts),
        'type': msg_type,
        'body': body,
        'status': 'queued'
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


def cancel(bridge: Path, target: str | None):
    ensure_bridge(bridge)
    body = 'CANCEL_ALL' if not target else f'CANCEL:{target}'
    return write_msg(bridge, 'all', body, msg_type='control')


def main():
    ap = argparse.ArgumentParser(prog='mission-control', description='Multi-agent CLI coordinator')
    ap.add_argument('--bridge', default=str(DEFAULT_BRIDGE), help='Bridge folder path')
    sub = ap.add_subparsers(dest='cmd', required=True)

    sub.add_parser('discover', help='Detect installed CLI agents')

    p_inst = sub.add_parser('install', help='Install one or all agents')
    p_inst.add_argument('agent', choices=['codex', 'gemini', 'qwen', 'all'])

    p_dispatch = sub.add_parser('dispatch', help='Send instruction to one/all agents')
    p_dispatch.add_argument('to', help='codex|gemini|qwen|all')
    p_dispatch.add_argument('body', help='Instruction text')

    sub.add_parser('status', help='Show inbox/outbox/state summary')

    p_cancel = sub.add_parser('cancel', help='Cancel operations')
    p_cancel.add_argument('--target', default='', help='optional target task/agent')

    args = ap.parse_args()
    bridge = Path(args.bridge)

    if args.cmd == 'discover':
        print(json.dumps(detect_agents(), indent=2))
        return

    if args.cmd == 'install':
        names = ['codex', 'gemini', 'qwen'] if args.agent == 'all' else [args.agent]
        result = {}
        for n in names:
            rc = install_agent(n)
            result[n] = {'rc': rc}
        print(json.dumps(result, indent=2))
        return

    if args.cmd == 'dispatch':
        targets = ['codex', 'gemini', 'qwen'] if args.to == 'all' else [args.to]
        files = [str(write_msg(bridge, t, args.body)) for t in targets]
        print(json.dumps({'queued': files}, indent=2))
        return

    if args.cmd == 'status':
        ensure_bridge(bridge)
        data = {
            'bridge': str(bridge),
            'counts': {
                'inbox': len(list((bridge / 'inbox').glob('*.json'))),
                'outbox': len(list((bridge / 'outbox').glob('*.json'))),
                'state': len(list((bridge / 'state').glob('*.json'))),
            },
            'state': read_json_files(bridge / 'state')
        }
        print(json.dumps(data, indent=2))
        return

    if args.cmd == 'cancel':
        f = cancel(bridge, args.target or None)
        print(json.dumps({'cancel_msg': str(f)}, indent=2))
        return

if __name__ == '__main__':
    main()
