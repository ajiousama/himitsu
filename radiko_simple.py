#!/usr/bin/env python3
import os, sys, getpass, traceback

os.environ.setdefault('RADIKO_PROXY_HOST','127.0.0.1')
os.environ.setdefault('RADIKO_PROXY_PORT','9495')

try:
    import radiko_proxy_core as core
except Exception as e:
    print(f'[simple] core import failed: {type(e).__name__}: {e}', flush=True)
    raise

print(f'[simple] core build={getattr(core,"BUILD","unknown")}', flush=True)

if not os.environ.get('RADIKO_MAIL','').strip():
    os.environ['RADIKO_MAIL'] = input('radiko mail address (Enter=local only): ').strip()
if os.environ.get('RADIKO_MAIL','').strip() and not os.environ.get('RADIKO_PASSWORD','').strip():
    os.environ['RADIKO_PASSWORD'] = getpass.getpass('radiko Premium password: ')

stages=[]
try:
    local=core.local_area(force=True)
    stages.append(f'local_area={local}')
    print('[simple] local area OK:', local, flush=True)

    if os.environ.get('RADIKO_MAIL','').strip() and os.environ.get('RADIKO_PASSWORD','').strip():
        core.premium_login(force=True)
        stages.append('premium_login=OK')
        print('[simple] Premium login OK', flush=True)
    else:
        print('[simple] Premium login skipped (local only)', flush=True)

    core.auth_area(local, force=True)
    stages.append('auth=OK')
    print('[simple] auth1/auth2 OK', flush=True)

except Exception as e:
    print('\n[simple] FAILED', flush=True)
    print('[simple] stages:', ', '.join(stages) if stages else 'none', flush=True)
    print(f'[simple] error={type(e).__name__}: {e}', flush=True)
    print('\nPress Enter to close...', flush=True)
    input()
    sys.exit(1)

print('\n[simple] READY', flush=True)
print('[simple] playlist: http://127.0.0.1:9495/playlist.m3u', flush=True)
print('[simple] ready:    http://127.0.0.1:9495/ready', flush=True)
print('[simple] No Tailscale / Funnel / public gateway in this mode.', flush=True)

core.HOST='127.0.0.1'
core.PORT=9495
core.main()
