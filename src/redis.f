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

fn(redis_get(client, key)) {
    return redis_cli_json(client.conn + ["GET", key])
}
fn(redis_set(client, key, value)) {
    return redis_cli_json(client.conn + ["SET", key, value])
}
fn(redis_del(client, key)) {
    return redis_cli_json(client.conn + ["DEL", key])
}
fn(redis_exists(client, key)) {
    return redis_cli_json(client.conn + ["EXISTS", key])
}
fn(redis_expire(client, key, seconds)) {
    return redis_cli_json(client.conn + ["EXPIRE", key, seconds.to_string()])
}

fn(redis_command(client, ...rest)) {
    return redis_cli_json(client.conn + rest)
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