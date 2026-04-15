# FlowSQL

Cliente de banco de dados desktop com interface idêntica ao SQL Server Management Studio (SSMS).

## Requisitos

- Python 3.8+
- PyQt5
- SQLAlchemy

## Instalação

```bash
pip install -r requirements.txt
```

## Execução

```bash
python main.py
```

## Bancos Suportados

- PostgreSQL
- MySQL
- Microsoft SQL Server
- SQLite

## Estrutura

```
flowsql/
├── main.py
├── requirements.txt
├── app/               ← Módulos de interface
├── core/              ← Backend e conexões
├── themes/            ← Temas QSS
└── assets/icons/      ← Ícones SVG
```
