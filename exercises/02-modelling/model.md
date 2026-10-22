#### 1. An ER diagram in Mermaid, with cardinalities. ####

# Biblioteca municipal: diagrama ER

```mermaid
erDiagram
    READER ||--o{ LOAN : "faz"
    READER ||--o{ RESERVATION : "faz"
    COPY ||--o{ LOAN : "é emprestado em"
    BOOK ||--o{ COPY : "tem"
    BOOK ||--o{ RESERVATION : "é reservado em"
    PUBLISHER ||--o{ BOOK : "publica"
    BOOK ||--|{ BOOK_AUTHOR : "tem"
    AUTHOR ||--o{ BOOK_AUTHOR : "escreve"
    LOAN ||--o| FINE : "pode gerar"

    READER {
        int id PK
        string name
        string nif UK
        string email UK
        string phone
        string address
        date registered_at
    }

    PUBLISHER {
        int id PK
        string name
        string country
    }

    AUTHOR {
        int id PK
        string name
        string nationality
    }

    BOOK {
        int id PK
        string title
        string isbn UK
        int publication_year
        int publisher_id FK
    }

    BOOK_AUTHOR {
        int book_id PK, FK
        int author_id PK, FK
    }

    COPY {
        int id PK
        int book_id FK
        string barcode UK
        string status
    }

    LOAN {
        int id PK
        int reader_id FK
        int copy_id FK
        date loan_date
        date due_date
        date return_date
    }

    RESERVATION {
        int id PK
        int reader_id FK
        int book_id FK
        datetime reserved_at
        datetime expires_at
        string status
    }

    FINE {
        int id PK
        int loan_id FK, UK
        decimal amount
        date issued_at
        date paid_at
    }
```

## Cardinalidades

| Relação | Cardinalidade | Leitura |
|---|---|---|
| Reader — Loan | 1 : N | Um leitor faz zero ou mais empréstimos; cada empréstimo é de um só leitor |
| Reader — Reservation | 1 : N | Um leitor faz zero ou mais reservas; cada reserva é de um só leitor |
| Book — Copy | 1 : N | Um livro tem zero ou mais exemplares; cada exemplar é de um só livro |
| Copy — Loan | 1 : N | Um exemplar pode ser emprestado várias vezes ao longo do tempo; cada empréstimo é de um só exemplar |
| Book — Reservation | 1 : N | Um livro pode ter várias reservas; cada reserva é de um só livro |
| Publisher — Book | 1 : N | Uma editora publica zero ou mais livros; cada livro tem uma só editora |
| Book — Author | N : M | Um livro tem um ou mais autores e um autor escreve zero ou mais livros (tabela de ligação `BOOK_AUTHOR`) |
| Loan — Fine | 1 : 0..1 | Um empréstimo gera no máximo uma multa; cada multa pertence a um só empréstimo |

## Pressupostos

- A **reserva é feita a um livro** (título) e não a um exemplar concreto, porque o leitor quer "um exemplar disponível" e não um específico.
- O **empréstimo é de um exemplar** (`COPY`), que é o objeto físico, e não do livro.
- A **multa liga-se ao empréstimo** (atraso na devolução), e o leitor obtém-se através dele.
- `loan_id` em `FINE` é `UK` para garantir uma só multa por empréstimo.