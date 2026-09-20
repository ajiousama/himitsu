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


VOLATILE_JSON_KEYS = {'checked_at', 'generated_at', 'schedule_checked_at', 'sequence', 'last_segment'}


def semantic_json_bytes(data):
    """Remove heartbeat-only fields before deciding whether a commit is useful."""
    try:
        value = json.loads(data.decode('utf-8-sig'))
    except Exception:
        return data

    def clean(item):
        if isinstance(item, dict):
            return {key: clean(val) for key, val in item.items() if key not in VOLATILE_JSON_KEYS}
        if isinstance(item, list):
            return [clean(val) for val in item]
        return item

    return json.dumps(clean(value), ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def head_bytes(name):
    result = subprocess.run(['git', 'show', f'HEAD:{name}'], capture_output=True)
    return result.stdout if result.returncode == 0 else None


def meaningful_output_changed():
    """True only when BOAT content/state changed, not just timestamps/cycle heartbeat."""
    for name in OUTPUTS:
        if name == 'boat_worker_status.json':
            continue
        path = Path(name)
        if not path.exists():
            continue
        before = head_bytes(name)
        after = path.read_bytes()
        if before is None:
            return True
        if name.endswith('.json'):
            if semantic_json_bytes(before) != semantic_json_bytes(after):
                return True
        elif before != after:
            return True
    return False


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
        # The worker polls every minute, but timestamps/cycle counters alone must not
        # create a repository commit. Real stream/EPG/status changes still publish immediately.
        if not meaningful_output_changed():
            print('BOAT content unchanged; heartbeat commit skipped')
            return
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
