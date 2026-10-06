# redis

Redis database package for Nift.

Runtime dependency: the `redis-cli` executable on `PATH` (v6+ for `--json`
output). The package drives `redis-cli` through Nift's structured process API
(argv, never shell concatenation). The v0.1.0 backend may change later without
requiring consumers to rewrite around it.

Redis is not relational, so the API deliberately does not mirror the SQL
packages.

## Installation

```text
nift add nift-packages/redis
```

## Import

```text
@import("redis")
```

## API

The exported `redis` struct:

```text
redis.available()                          // bool: redis-cli on PATH and process execution enabled
redis.version()                             // redis-cli --version first line, or "" when unavailable
client := redis.open({...})                // descriptor: host/port/db
redis.get(client, key)                     // {ok, data, error, error_code, exit_code}
redis.set(client, key, value)              // data = "OK"
redis.del(client, key)                     // data = number of deleted keys
redis.exists(client, key)                  // data = 0 or 1
redis.expire(client, key, seconds)         // data = 0 or 1
redis.command(client, ...args)             // generic escape hatch
```

`open` accepts `host` (default 127.0.0.1), `port` (default 6379) and `db`
(default 0). Use a dedicated `db` (e.g. 15) for scratch data.

```text
@import("redis")

client := redis.open({"host": "127.0.0.1", "port": 6379, "db": 15})
redis.set(client, "greeting", "hello")
print(redis.get(client, "greeting").data)
redis.del(client, "greeting")
```

`redis.command` is the generic escape hatch so the package does not need a
wrapper for every command:

```text
redis.command(client, "HSET", "thing", "a", "1", "b", "2")
h := redis.command(client, "HGETALL", "thing")
print(h.data.a)
```

Replies are produced with `redis-cli --json` and parsed into Nift values:
strings, numbers, `null` for missing keys, and objects for hashes/maps.

## Result shape

Every call returns `{ok, data, error, error_code, exit_code}`. `data` is the
parsed reply (`null` when a key is missing).

`error_code` values:

```text
backend_unavailable   redis-cli is missing or process execution is disabled (exit_code 127)
invalid_input         a command name/argument is invalid, non-scalar, or contains NUL (exit_code 2)
temporary_file        a temporary reply file could not be created
operation_failed      redis-cli exited non-zero; error carries stderr
```

## Argument safety

Every command is built as an independent argv list (`redis-cli --json …`), never
a shell string. `redis-cli` does not accept a `--` terminator, but trailing
keys/values follow the command token and are treated as data, so only the
command name itself can be mistaken for an option; a command name beginning with
`-` is rejected with `invalid_input`. Non-scalar and NUL-containing arguments are
also rejected.

## Credentials

The package intentionally exposes no password/TLS options. If your server
requires authentication, configure `redis-cli` itself (for example
`REDISCLI_AUTH` in the environment); the package never prints or forwards
credentials and no secret is placed on the command line by the package.

## Availability

`available()` is false when `redis-cli` is missing or Nift runs with
`--no-process` (`NIFT_NO_PROCESS`). Operations then return a recoverable
`backend_unavailable` result without launching the process.

## Limitations (v0.1.0)

- Requires a reachable Redis server; use an isolated `db` for scratch data.
- The generic command escape hatch passes arguments through verbatim; complex
  value encoding is the caller's responsibility.

## Tests

```sh
python3 -B tests/test_redis.py /path/to/nift
```

The suite uses a fake `redis-cli` for argv/security boundaries and runs isolated
integration (unique key namespace, cleaned up) when a local Redis server is
reachable.

Version: 0.1.0
