/*
Redis database package for Nift. v0.1.0 backend: the redis-cli executable.
Public API: the exported `redis` struct. Helpers stay private.
redis-cli --json gives machine-readable replies; a temp file bridges the
JSON output into Nift values (the language has no JSON-string parser yet).
*/

fn(redis_available()) { return which("redis-cli") != null }

fn(redis_version_text()) {
    r := run("redis-cli", "--version")
    if(r.exit_code != 0) { return "" }
    return r.stdout.trim()
}

fn(redis_open_desc(desc)) {
    args := []
    host := "127.0.0.1"
    port := 6379
    db := 0
    if(desc != null) {
        host = desc.get("host", "127.0.0.1")
        port = desc.get("port", 6379)
        db = desc.get("db", 0)
    }
    args.push("-h"); args.push(host)
    args.push("-p"); args.push(port.to_string())
    args.push("-n"); args.push(db.to_string())
    return {"conn": args}
}

fn(redis_temp_file()) {
    m := run("mktemp", "--suffix=.json")
    if(m.exit_code != 0) { return "" }
    return m.stdout.trim()
}

fn(redis_cli_json(args)) {
    if(!redis_available()) { return {"ok":false,"data":null,"error":"redis-cli executable not found","exit_code":127} }
    temp := redis_temp_file()
    if(temp == "") { return {"ok":false,"data":null,"error":"no temp file available","exit_code":1} }
    result := cmd("redis-cli", "--json", ...args).stdout(temp).run()
    if(result.exit_code != 0) {
        remove(temp)
        return {"ok":false,"data":null,"error":result.stderr,"exit_code":result.exit_code}
    }
    text := open(temp).trim()
    if(text.empty()) { remove(temp); return {"ok":true,"data":null,"error":"","exit_code":0} }
    data := inject(temp)
    remove(temp)
    return {"ok":true,"data":data,"error":"","exit_code":0}
}

fn(redis_copy(base)) {
    out := []
    for(item : base) { out.push(item) }
    return out
}

fn(redis_get(client, key)) {
    args := redis_copy(client.conn); args.push("GET"); args.push(key)
    return redis_cli_json(args)
}
fn(redis_set(client, key, value)) {
    args := redis_copy(client.conn); args.push("SET"); args.push(key); args.push(value)
    return redis_cli_json(args)
}
fn(redis_del(client, key)) {
    args := redis_copy(client.conn); args.push("DEL"); args.push(key)
    return redis_cli_json(args)
}
fn(redis_exists(client, key)) {
    args := redis_copy(client.conn); args.push("EXISTS"); args.push(key)
    return redis_cli_json(args)
}
fn(redis_expire(client, key, seconds)) {
    args := redis_copy(client.conn); args.push("EXPIRE"); args.push(key); args.push(seconds.to_string())
    return redis_cli_json(args)
}

fn(redis_command(client, ...rest)) {
    args := redis_copy(client.conn)
    for(item : rest) { args.push(item) }
    return redis_cli_json(args)
}

@struct(redis_api) {
    available := () => redis_available()
    version := () => redis_version_text()
    open := (desc) => redis_open_desc(desc)
    get := (client, key) => redis_get(client, key)
    set := (client, key, value) => redis_set(client, key, value)
    del := (client, key) => redis_del(client, key)
    exists := (client, key) => redis_exists(client, key)
    expire := (client, key, seconds) => redis_expire(client, key, seconds)
    command := (client, ...rest) => redis_command(client, ...rest)
}

redis := redis_api()
export(redis)