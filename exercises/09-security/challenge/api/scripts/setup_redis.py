"""Cria os utilizadores ACL do Redis das duas instâncias. Pode correr mais do que uma vez.

ex09_app    (instância A): INCR e GET em counter:*
ex09_reader (instância B): só GET em counter:*

Corre como o utilizador default (REDIS_ADMIN_URL do .env.setup). Os comandos recusados só
são enviados depois de ACL DRYRUN confirmar que o ACL os recusa.
"""

import os

import redis
from dotenv import load_dotenv

load_dotenv(".env.setup")

USERS = {
    "ex09_app": (os.environ["REDIS_APP_PASSWORD"], ["+incr", "+get"]),
    "ex09_reader": (os.environ["REDIS_READER_PASSWORD"], ["+get"]),
}
PROBES = [("INCR", "counter:setup_probe"), ("GET", "counter:setup_probe"), ("SET", "counter:setup_probe", "1"), ("GET", "other:key")]


def main() -> None:
    admin = redis.Redis.from_url(os.environ["REDIS_ADMIN_URL"], decode_responses=True)
    for user, (password, commands) in USERS.items():
        # reset: começa sem nenhuma permissão. ~counter:*: só chaves counter:. -@all: nenhum comando além dos listados.
        admin.execute_command("ACL", "SETUSER", user, "reset", "on", f">{password}", "~counter:*", "resetchannels", "-@all", *commands)
        print(f"ACL SETUSER {user} reset on >*** ~counter:* resetchannels -@all {' '.join(commands)}")
        for command in PROBES:
            verdict = admin.execute_command("ACL", "DRYRUN", user, *command)
            print(f"  {' '.join(command):<28} -> {'allowed' if verdict == 'OK' else verdict}")


if __name__ == "__main__":
    main()
