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
redis.available()                          // bool: redis-cli on PATH
redis.version()                            // redis-cli --version first line
client := redis.open({...})                // descriptor: host/port/db
redis.get(client, key)                     // {ok, data, error, exit_code}
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

Every call returns `{ok, data, error, exit_code}`. `data` is the parsed reply
(`null` when a key is missing). `exit_code` is `127` when `redis-cli` is
missing.

## Limitations (v0.1.0)

- Requires a reachable Redis server; use an isolated `db` for scratch data.
- The generic command escape hatch passes arguments through verbatim; complex
  value encoding is the caller's responsibility.

Version: 0.1.0