# Desafio 05: Graus de separação com `WITH RECURSIVE`

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `degrees.sql` | A CTE `edge` (tarefa 1), a pesquisa a 3 graus do ator 1 (tarefa 2), o resumo por distância e o caminho mais curto de 1 a 200 (tarefa 3) |
| `README.md` | Este ficheiro |

## Como correr

A partir da raiz do repositório:

```bash
./scripts/create-db.sh ch05 --pagila --reset
docker compose exec -T postgres psql -U postgres -d ch05 -v ON_ERROR_STOP=1 < exercises/05-queries/challenge/degrees.sql
```

O ficheiro corre em menos de meio segundo.

## Tarefa 1: as arestas

```sql
edge (actor_id, other_actor_id) AS (
    SELECT fa1.actor_id, fa2.actor_id
    FROM film_actor fa1
    JOIN film_actor fa2 ON fa2.film_id = fa1.film_id AND fa2.actor_id <> fa1.actor_id
    GROUP BY fa1.actor_id, fa2.actor_id
    HAVING count(*) >= 3
)
```

O self join de `film_actor` com `<>` (e não `<`) gera cada par nos dois sentidos, `(a, b)` e `(b, a)`, e o `HAVING count(*) >= 3` guarda só os pares com 3 ou mais filmes juntos. São 1650 arestas dirigidas (825 pares).

## Tarefa 2: atores a 3 graus ou menos do ator 1

141 atores. Número de atores a cada distância:

```
 distance | actors
----------+--------
        1 |      3
        2 |     23
        3 |    115
(3 rows)
```

Início e fim do resultado (ordenado por distância e `actor_id`):

```
 actor_id | first_name  |  last_name   | distance
----------+-------------+--------------+----------
        4 | JENNIFER    | DAVIS        |        1
       20 | LUCILLE     | TRACY        |        1
       64 | RAY         | JOHANSSON    |        1
        7 | GRACE       | MOSTEL       |        2
       13 | UMA         | WOOD         |        2
       16 | FRED        | COSTNER      |        2
       17 | HELEN       | VOIGHT       |        2
 ...
      192 | JOHN        | SUVARI       |        3
      195 | JAYNE       | SILVERSTONE  |        3
      196 | BELA        | WALKEN       |        3
(141 rows)
```

O ator 1 tem 3 ligações diretas (atores 4, 20 e 64), e o ator 1 não aparece no resultado.

### Verificação

Confirmei os números com uma pesquisa diferente, sem arrays: uma pesquisa em largura que só guarda `(actor_id, distance)` e usa `UNION` (que remove repetidos) em vez de `UNION ALL`, limitada pela distância.

```sql
bfs(actor_id, d) AS (SELECT 1, 0 UNION SELECT e.b, bfs.d + 1 FROM bfs JOIN edge e ON e.a = bfs.actor_id WHERE bfs.d < 5)
```

```
 distance | actors | has_200
----------+--------+---------
        1 |      3 | f
        2 |     23 | f
        3 |    115 | f
        4 |     53 | t
        5 |      4 | f
```

As distâncias 1 a 3 batem certo (3, 23, 115). A pesquisa mostra também que o ator 200 está a distância 4, o que confirma a tarefa 3. No total, 198 atores estão ligados ao ator 1. Dos 200 atores, um não tem nenhuma ligação com 3 ou mais filmes.

## Tarefa 3: caminho mais curto do ator 1 ao ator 200

```
 step | actor_id |      actor
------+----------+------------------
    0 |        1 | PENELOPE GUINESS
    1 |       20 | LUCILLE TRACY
    2 |      107 | GINA DEGENERES
    3 |       76 | ANGELINA ASTAIRE
    4 |      200 | THORA TEMPLE
(5 rows)
```

4 graus de separação. Cada passo é uma aresta válida:

```
  a  |  b  | films_together
-----+-----+----------------
   1 |  20 |              3
  20 | 107 |              4
 107 |  76 |              3
  76 | 200 |              3
```

Pode haver outros caminhos com o mesmo comprimento. A consulta ordena por `distance, path` e fica com o primeiro, para devolver sempre o mesmo. Se não houvesse caminho em 5 graus ou menos, `best` ficava vazio e o resultado também.

## Como a consulta evita correr para sempre

O grafo tem ciclos: se A está ligado a B, B também está ligado a A. Sem proteção, a recursão andava A → B → A → B ... para sempre. A consulta tem três travões:

1. **Limite de profundidade.** `WHERE s.distance < 3` (ou `< 5` na tarefa 3). Cada iteração soma 1 à distância, e quando a última linha nova chega ao limite deixa de gerar linhas. A recursão do PostgreSQL termina quando uma iteração não produz nenhuma linha nova.
2. **Caminho num array.** Cada linha leva o caminho percorrido (`path`), e `e.other_actor_id <> ALL (s.path)` impede que um ator volte a ser visitado no mesmo caminho. Assim não há ciclos dentro de um caminho, e o número de caminhos é finito mesmo sem o limite de profundidade. O limite continua a ser necessário para não enumerar todos os caminhos simples do grafo, que seriam muitíssimos.
3. **Paragem no destino (tarefa 3).** `s.actor_id <> 200` faz com que um caminho que já chegou ao ator 200 não continue a crescer.

O mesmo ator pode aparecer em vários caminhos com distâncias diferentes. Por isso a tarefa 2 usa `min(distance)` por ator para ficar com a distância mais curta.
