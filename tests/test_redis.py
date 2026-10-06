#!/usr/bin/env python3
"""Deterministic contract/security tests for the redis Nift package.

A fake `redis-cli` records exact argv. If a local Redis server is reachable,
isolated integration runs against a random key namespace that is cleaned up.
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

NIFT = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/nick/Repositories/nift/nift/nift").resolve()
PACKAGE = Path(__file__).resolve().parent.parent
TESTS = PACKAGE / "tests"
SOURCE = PACKAGE / "src" / "redis.f"

manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
if manifest != {"name": "redis", "version": "0.1.0", "entry": "src/redis.f", "description": "Redis database package"}:
    raise SystemExit(f"FAIL unexpected package manifest: {manifest!r}")

source = SOURCE.read_text(encoding="utf-8")
exports = re.findall(r"^export\(([^)]+)\)$", source, re.MULTILINE)
public_methods = re.findall(r"^    fn\(([A-Za-z_][A-Za-z0-9_]*)\(", source, re.MULTILINE)
expected_public = ["available", "version", "open", "get", "set", "del", "exists", "expire", "command"]
if exports != ["redis"] or public_methods != expected_public:
    raise SystemExit(f"FAIL unexpected public surface: exports={exports!r} methods={public_methods!r}")

FAKE = r"""#!/usr/bin/env bash
n=0
if [ -f "${REDIS_CAPTURE}.count" ]; then n=$(cat "${REDIS_CAPTURE}.count"); fi
dir="${REDIS_CAPTURE}.call${n}"
mkdir -p "$dir"
i=0
for a in "$@"; do printf '%s' "$a" > "$dir/$i"; i=$((i+1)); done
echo $((n+1)) > "${REDIS_CAPTURE}.count"
for a in "$@"; do
  if [ "$a" = "--version" ]; then echo "redis-cli 8.0.5"; exit 0; fi
done
cmd=""
skip=0
for a in "$@"; do
  if [ "$skip" = "1" ]; then skip=0; continue; fi
  case "$a" in
    --json) ;;
    -h|-p|-n) skip=1;;
    -*) ;;
    *) cmd="$a"; break;;
  esac
done
for a in "$@"; do
  if [ "$a" = "missing" ]; then printf 'null'; exit 0; fi
done
case "$cmd" in
  GET) printf '"value"';;
  SET) printf '"OK"';;
  DEL) printf '1';;
  EXISTS) printf '1';;
  EXPIRE) printf '1';;
  PING) printf '"PONG"';;
  HGETALL) printf '{"a":"1","b":"2"}';;
  *) printf 'null';;
esac
exit 0
"""


def require(condition, message, result=None):
    if condition:
        return
    if result is not None:
        message += f"\nstdout: {result.stdout!r}\nstderr: {result.stderr!r}\nreturn code: {result.returncode}"
    raise SystemExit("FAIL " + message)


def run(args, cwd, env):
    return subprocess.run([str(NIFT), *args], cwd=cwd, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=60, check=False, env=env)


def base_env(bin_dir, capture, tmp):
    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}:/usr/bin:/bin"
    env["REDIS_CAPTURE"] = str(capture)
    env["TMPDIR"] = str(tmp)
    env["TEMP"] = str(tmp)
    env["TMP"] = str(tmp)
    env.pop("NIFT_NO_PROCESS", None)
    return env


def clear_capture(capture):
    for path in Path(capture).parent.glob(Path(capture).name + "*"):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)


def calls(capture):
    parsed = []
    index = 0
    while True:
        directory = Path(f"{capture}.call{index}")
        if not directory.is_dir():
            break
        args = []
        i = 0
        while (directory / str(i)).exists():
            args.append((directory / str(i)).read_text(encoding="utf-8"))
            i += 1
        parsed.append(args)
        index += 1
    return parsed


def nift_string(text):
    if text == "":
        return '""'
    return "bytes([" + ",".join(str(b) for b in text.encode("utf-8")) + ']).decode("utf-8")'


WORK = Path(tempfile.mkdtemp(prefix=".redis-tests-", dir=TESTS))
try:
    fake_bin = WORK / "bin"
    fake_bin.mkdir()
    fake = fake_bin / "redis-cli"
    fake.write_text(FAKE, encoding="utf-8")
    fake.chmod(0o755)
    tmpdir = WORK / "tmp"
    tmpdir.mkdir()

    consumer = WORK / "consumer"
    consumer.mkdir()
    (consumer / ".nift").mkdir()
    added = run(["add", str(PACKAGE)], consumer, base_env(fake_bin, WORK / "add.txt", tmpdir))
    require(added.returncode == 0, "nift add into fresh consumer failed", added)

    def run_script(name, body, env=None, capture="cap.txt"):
        capfile = WORK / capture
        clear_capture(capfile)
        (consumer / name).write_text(body, encoding="utf-8")
        return run([name], consumer, env or base_env(fake_bin, capfile, tmpdir))

    # 1. Structured argv for hostile keys/values.
    key = "k; $(touch " + str(WORK / "pwned") + ") `id` é😀-\n"
    value = "v; $(touch " + str(WORK / "pwned2") + ") & |"
    cap = WORK / "argv.txt"
    body = ('@import("redis")\n'
            'c := redis.open({"host":"127.0.0.1","port":6379,"db":0})\n'
            'r := redis.set(c, ' + nift_string(key) + ', ' + nift_string(value) + ')\n'
            'print(r.ok.to_string() + " " + r.data)\n')
    res = run_script("argv.f", body, capture="argv.txt")
    require(res.returncode == 0 and res.stdout.strip() == "true OK", "hostile set failed", res)
    argv = calls(cap)[0]
    require(argv == ["--json", "-h", "127.0.0.1", "-p", "6379", "-n", "0", "SET", key, value],
            f"hostile redis argv wrong: {argv!r}")
    require(not (WORK / "pwned").exists() and not (WORK / "pwned2").exists(), "argument caused shell side effect")

    # 2. Dash-prefixed keys/values are safe (they follow the command token).
    cap = WORK / "dashkey.txt"
    body = ('@import("redis")\nc := redis.open({})\nprint(redis.get(c, "-dash-key").ok.to_string())\n')
    res = run_script("dashkey.f", body, capture="dashkey.txt")
    require(res.returncode == 0 and res.stdout.strip() == "true", "dash key failed", res)
    require(calls(cap)[0][-2:] == ["GET", "-dash-key"], f"dash key argv wrong: {calls(cap)[0]!r}")

    # 3. Command-name validation blocks option injection through the generic hatch.
    for index, call in enumerate(['redis.command(c, "-h", "evil")', 'redis.command(c, "")', 'redis.command(c, 7)', 'redis.command(c)']):
        res = run_script(f"badcmd{index}.f",
                         '@import("redis")\nc := redis.open({})\nr := ' + call + '\nprint(r.error_code)\n',
                         capture="badcmd.txt")
        require(res.returncode == 0 and res.stdout.strip() == "invalid_input",
                f"bad command case {index} not rejected: {res.stdout!r} {res.stderr!r}")
    require(calls(WORK / "badcmd.txt") == [], "invalid command still launched redis-cli")

    # 4. Non-scalar and NUL arguments are rejected.
    bad_args = [
        'redis.set(c, {"a":1}, "v")',
        'redis.set(c, "k", [1,2])',
        'redis.set(c, "k", bytes([0]).decode("utf-8"))',
    ]
    for index, call in enumerate(bad_args):
        res = run_script(f"badarg{index}.f",
                         '@import("redis")\nc := redis.open({})\nprint(' + call + '.error_code)\n',
                         capture="badarg.txt")
        require(res.returncode == 0 and res.stdout.strip() == "invalid_input",
                f"bad arg case {index} not rejected: {res.stdout!r} {res.stderr!r}")

    # 5. Parsed JSON replies (string, number, object, null).
    cap = WORK / "replies.txt"
    body = ('@import("redis")\nc := redis.open({})\n'
            'print(redis.get(c, "k").data)\n'
            'print(redis.exists(c, "k").data.to_string())\n'
            'print(redis.command(c, "HGETALL", "h").data.a)\n'
            'print(redis.get(c, "missing").data == null)\n')
    res = run_script("replies.f", body, capture="replies.txt")
    require(res.returncode == 0 and res.stdout.strip().splitlines() == ["value", "1", "1", "true"],
            f"reply parsing wrong: {res.stdout!r} {res.stderr!r}")

    # 6. Missing executable and --no-process fail closed without launching.
    empty_bin = WORK / "emptybin"
    empty_bin.mkdir()
    missing_env = dict(os.environ)
    missing_env["PATH"] = str(empty_bin)
    missing_env["REDIS_CAPTURE"] = str(WORK / "missing.txt")
    missing_env["TMPDIR"] = str(tmpdir); missing_env["TEMP"] = str(tmpdir); missing_env["TMP"] = str(tmpdir)
    missing_env.pop("NIFT_NO_PROCESS", None)
    probe = """@import("redis")
print(redis.available().to_string())
print(redis.version() == "")
c := redis.open({})
r := redis.get(c, "k")
print(r.ok.to_string() + ":" + r.error_code + ":" + r.exit_code.to_string())
"""
    res = run_script("missing.f", probe, env=missing_env, capture="missing.txt")
    require(res.returncode == 0 and res.stdout.strip().splitlines() == ["false", "true", "false:backend_unavailable:127"],
            f"missing executable behavior wrong: {res.stdout!r} {res.stderr!r}")

    noproc = base_env(fake_bin, WORK / "noproc.txt", tmpdir)
    noproc["NIFT_NO_PROCESS"] = "1"
    clear_capture(WORK / "noproc.txt")
    res = run_script("noproc.f", probe, env=noproc, capture="noproc.txt")
    require(res.returncode == 0 and res.stdout.strip().splitlines() == ["false", "true", "false:backend_unavailable:127"],
            f"--no-process behavior wrong: {res.stdout!r} {res.stderr!r}")
    require(calls(WORK / "noproc.txt") == [], "--no-process still launched redis-cli")

    # 7. Temporary files are cleaned up.
    body = '@import("redis")\nc := redis.open({})\nredis.get(c, "k")\nredis.set(c, "k", "v")\n'
    res = run_script("temps.f", body, capture="temps.txt")
    require(res.returncode == 0, "temp cleanup run failed", res)
    leftovers = [name for name in os.listdir(tmpdir) if name.startswith(".nift-redis-")]
    require(not leftovers, f"redis temp files leaked: {leftovers}")

    # 8. Privacy.
    for helper in ["process_available", "failure", "is_scalar", "has_nul", "temp_root", "temp_file", "cli_json"]:
        (consumer / "privacy.f").write_text(f'@import("redis")\nredis.{helper}("x")\n', encoding="utf-8")
        res = run(["privacy.f"], consumer, base_env(fake_bin, WORK / "privacy.txt", tmpdir))
        require(res.returncode != 0, f"private helper {helper} was accessible")
    (consumer / "privateglobal.f").write_text('@import("redis")\nprint(redis_temp_seq)\n', encoding="utf-8")
    require(run(["privateglobal.f"], consumer, base_env(fake_bin, WORK / "privglobal.txt", tmpdir)).returncode != 0,
            "module global redis_temp_seq leaked")
    (consumer / "privateglobal2.f").write_text('@import("redis")\nprint(redis_nul)\n', encoding="utf-8")
    require(run(["privateglobal2.f"], consumer, base_env(fake_bin, WORK / "privglobal2.txt", tmpdir)).returncode != 0,
            "module global redis_nul leaked")

    # 9. Determinism.
    body = '@import("redis")\nc := redis.open({})\nredis.set(c, "k", "v")\n'
    (consumer / "det.f").write_text(body, encoding="utf-8")
    a, b = WORK / "det_a.txt", WORK / "det_b.txt"
    for capfile in (a, b):
        clear_capture(capfile)
        r = run(["det.f"], consumer, base_env(fake_bin, capfile, tmpdir))
        require(r.returncode == 0, "determinism run failed", r)
    require(calls(a) == calls(b), "argv not deterministic")

    # 10. Isolated real integration if a local Redis is reachable.
    real = shutil.which("redis-cli")
    reachable = False
    if real:
        ping = subprocess.run([real, "-h", "127.0.0.1", "-p", "6379", "PING"], capture_output=True, text=True)
        reachable = ping.returncode == 0 and "PONG" in ping.stdout
    if reachable:
        real_env = dict(os.environ)
        real_env["PATH"] = "/usr/bin:/bin"
        real_env["TMPDIR"] = str(tmpdir); real_env["TEMP"] = str(tmpdir); real_env["TMP"] = str(tmpdir)
        real_env.pop("NIFT_NO_PROCESS", None)
        token = "nift-audit-" + uuid.uuid4().hex
        real_script = ('@import("redis")\n'
                       'c := redis.open({"host":"127.0.0.1","port":6379,"db":0})\n'
                       'print(redis.set(c, ' + nift_string(token) + ', "hello").data)\n'
                       'print(redis.get(c, ' + nift_string(token) + ').data)\n'
                       'print(redis.exists(c, ' + nift_string(token) + ').data.to_string())\n'
                       'print(redis.del(c, ' + nift_string(token) + ').data.to_string())\n'
                       'print(redis.get(c, ' + nift_string(token) + ').data == null)\n')
        res = run_script("real.f", real_script, env=real_env, capture="real.txt")
        require(res.returncode == 0 and res.stdout.strip().splitlines() == ["OK", "hello", "1", "1", "true"],
                f"real redis integration wrong: {res.stdout!r} {res.stderr!r}")
        subprocess.run([real, "-h", "127.0.0.1", "-p", "6379", "-n", "0", "DEL", token], capture_output=True)
    else:
        print("SKIP real redis integration (no reachable server)")

finally:
    shutil.rmtree(WORK, ignore_errors=True)

print("PASS redis package tests")
