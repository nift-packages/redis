/*
    Redis database package for Nift. v0.1.0 backend: the redis-cli executable.
    Public API: the exported `redis` struct. Helpers stay private.
    redis-cli --json gives machine-readable replies; a temp file bridges the
    JSON output into Nift values (the language has no JSON-string parser yet).
*/

struct(redis) {
    private fn(temp_file()) {
        m := run("mktemp", "--suffix=.json")
        if(m.exit_code != 0) { return "" }
        return m.stdout.trim()
    }

    private fn(cli_json(args)) {
        if(which("redis-cli") == null) { return {"ok":false,"data":null,"error":"redis-cli executable not found","exit_code":127} }
        temp := this.temp_file()
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

    fn(available()) { return which("redis-cli") != null }

    fn(version()) {
        r := run("redis-cli", "--version")
        if(r.exit_code != 0) { return "" }
        return r.stdout.trim()
    }

    fn(open(desc)) {
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

    fn(get(client, key)) {
        return this.cli_json(client.conn + ["GET", key])
    }

    fn(set(client, key, value)) {
        return this.cli_json(client.conn + ["SET", key, value])
    }

    fn(del(client, key)) {
        return this.cli_json(client.conn + ["DEL", key])
    }

    fn(exists(client, key)) {
        return this.cli_json(client.conn + ["EXISTS", key])
    }

    fn(expire(client, key, seconds)) {
        return this.cli_json(client.conn + ["EXPIRE", key, seconds.to_string()])
    }

    fn(command(client, ...rest)) {
        return this.cli_json(client.conn + rest)
    }
}

redis := redis()
export(redis)
