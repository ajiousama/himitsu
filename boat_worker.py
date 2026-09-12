"""Keep acquisition running between GitHub schedule events; publish by owned block."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time

STATE_FILES = ('boat_auto_state.json', 'today_boat_status.json', 'boat_auto_alert.json')
OUTPUTS = (*STATE_FILES, 'freewifi', 'guides.xml', 'public_sports_epg_local.xml',
           'today_event_counts.json', 'boat_worker_status.json', 'gccx2_live_state.json')


def run(*args, timeout=180):
    return subprocess.run(args, check=True, timeout=timeout)


def publish(snapshot):
    for attempt in range(5):
        run('git', 'fetch', 'origin', 'main')
        run('git', 'reset', '--hard', 'origin/main')
        for name, content in snapshot.items():
            Path(name).write_bytes(content)
        # Do not overwrite current freewifi/guides with the old checkout's copies.
        # boat_publish.py also refreshes the short-lived CX2 KICK URL.
        run('python', 'boat_publish.py')
        run('python', 'build_today_event_counts.py')
        run('git', 'add', *OUTPUTS)
        if subprocess.run(['git', 'diff', '--cached', '--quiet']).returncode == 0:
            return
        run('git', 'commit', '-m', 'Update BOAT verified streams and race EPG [skip ci] [skip render]')
        if subprocess.run(['git', 'push', 'origin', 'HEAD:main'], timeout=90).returncode == 0:
            return
    raise RuntimeError('BOAT publication failed after 5 concurrent-update retries')


def queue_successor():
    repo = os.environ['GITHUB_REPOSITORY']
    # workflow_dispatch is not delayed by the cron scheduler. Concurrency queues
    # the successor while the current worker finishes; it never cancels this run.
    run('gh', 'api', '-X', 'POST',
        f'repos/{repo}/actions/workflows/update_boat_auto.yml/dispatches', '-f', 'ref=main')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--duration', type=int, default=19800)
    args = parser.parse_args()
    run('git', 'config', 'user.name', 'github-actions[bot]')
    run('git', 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com')
    started = time.monotonic()
    successor = False
    cycles = 0
    while True:
        tick = time.monotonic()
        try:
            run('git', 'fetch', 'origin', 'main')
            run('git', 'reset', '--hard', 'origin/main')
            run('python', '-u', 'boat_auto_system.py', timeout=240)
            status = {'checked_at': datetime.now(timezone.utc).isoformat(),
                      'run_id': os.environ.get('GITHUB_RUN_ID'),
                      'cycles': cycles + 1, 'successor_queued': successor,
                      'strategy': 'continuous worker, 60-second retry; 5-minute verified-stream probes; CX2 token refresh'}
            snapshot = {name: Path(name).read_bytes() for name in STATE_FILES}
            snapshot['boat_worker_status.json'] = (json.dumps(status, indent=2) + '\n').encode()
            publish(snapshot)
            cycles += 1
        except Exception as exc:
            print(f'::error::BOAT worker cycle failed: {type(exc).__name__}', flush=True)
            if args.once:
                raise
        if args.once:
            break
        elapsed = time.monotonic() - started
        if elapsed >= args.duration - 1800 and not successor:
            try:
                queue_successor()
                successor = True
            except Exception as exc:
                print(f'::error::BOAT successor dispatch failed: {type(exc).__name__}', flush=True)
        if elapsed >= args.duration:
            if not successor:
                raise RuntimeError('no successor queued before worker shutdown')
            break
        time.sleep(max(1, 60 - (time.monotonic() - tick)))


if __name__ == '__main__':
    main()
