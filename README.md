# AI Financial Analyst

An AI-assisted financial analysis system that automates financial investigation, material-driver identification, and executive commentary generation from structured financial data.

## Project Overview

The AI Financial Analyst helps analysts investigate financial performance across multiple hierarchical dimensions.

The system:

- Compares current and previous quarter financial performance
- Identifies material Technical Result drivers
- Performs hierarchical drill-down across business dimensions
- Generates controlled SQL queries for evidence retrieval
- Validates and executes SQL against the financial database
- Generates evidence-based executive commentary
- Provides a conversational Data Assistant for natural-language financial queries

## Key Features

### Automated Financial Investigation

The Analyst Orchestrator progressively investigates financial movements across:

1. Accounting Year
2. Quarter
3. Main Line of Business
4. UW Portfolio
5. Cedent
6. Renewal / New Business / Cancelled

Material drivers are selected using an 80% contribution-based approach.

### Controlled SQL Generation

The SQL Agent converts analytical questions into controlled SQLite SELECT queries.

SQL is validated before execution to ensure that only safe database operations are performed.

### Executive Commentary

The system uses retrieved financial evidence and identified drivers to generate concise, management-oriented commentary explaining:

- What changed
- Where the change occurred
- What business areas contributed to the movement
- Which portfolios and cedents were material
- Renewal, New Business and Cancelled activity
- Management areas requiring attention

### Data Assistant

The conversational Data Assistant allows analysts to ask natural-language questions about the selected market and receive answers based on the underlying financial data.

## Technology Stack

- Python
- Streamlit
- SQLite
- Pandas
- OpenRouter
- Large Language Model (LLM)
- SQL-based financial analysis
- Multi-agent analytical workflow

## Project Structure

```text
Capstone 2 ProjectRepo/
│
├── agents/
│   ├── analyst_orchestrator.py
│   ├── sql_agent.py
│   └── data_chatbot.py
│
├── database/
│   └── schema_reader.py
│
├── llm/
│   └── openrouter_client.py
│
├── app.py
├── config.py
├── .env.example
├── .gitignore
└── README.md