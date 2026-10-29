"""Cria o utilizador ACL do Redis para a API. Pode correr mais do que uma vez.

Corre ACL SETUSER como o utilizador default (REDIS_ADMIN_URL) e depois liga-se como o novo
utilizador para mostrar o que pode e não pode fazer. Os comandos perigosos só são enviados
como ex09_app depois de ACL DRYRUN confirmar que o ACL os recusa: nunca correm a sério.
"""

import os

import redis
from dotenv import load_dotenv

load_dotenv()

USER = "ex09_app"
PASSWORD = os.environ["REDIS_APP_PASSWORD"]
# reset: começa sem nenhuma permissão, para que correr outra vez dê o mesmo resultado.
# ~counter:*: só chaves que começam por counter:.  -@all +incr: só o comando INCR.
RULES = ["reset", "on", f">{PASSWORD}", "~counter:*", "resetchannels", "-@all", "+incr"]


def main() -> None:
    admin = redis.Redis.from_url(os.environ["REDIS_ADMIN_URL"], decode_responses=True)
    admin.execute_command("ACL", "SETUSER", USER, *RULES)
    print(f"ACL SETUSER {USER} reset on >*** ~counter:* resetchannels -@all +incr")
    print(f"ACL GETUSER {USER}: commands={admin.acl_getuser(USER)['commands']} keys={admin.acl_getuser(USER)['keys']}")

    app = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    print(f"INCR counter:setup_probe -> {app.execute_command('INCR', 'counter:setup_probe')}")
    admin.delete("counter:setup_probe")

    probes = [
        ("INCRBY", "counter:setup_probe", "5"),
        ("INCR", "other:key"),
        ("GET", "counter:setup_probe"),
        ("SET", "counter:setup_probe", "1"),
        ("DEL", "counter:setup_probe"),
        ("FLUSHALL",),
        ("KEYS", "*"),
        ("CONFIG", "GET", "maxmemory"),
    ]
    for command in probes:
        label = " ".join(command)
        if admin.execute_command("ACL", "DRYRUN", USER, *command) == "OK":
            print(f"{label:<28} -> allowed by the ACL (not sent)")
            continue
        try:
            app.execute_command(*command)
        except redis.exceptions.NoPermissionError as exc:
            print(f"{label:<28} -> {exc}")


if __name__ == "__main__":
    main()
