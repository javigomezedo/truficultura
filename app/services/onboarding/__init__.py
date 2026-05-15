"""Historical-data onboarding agent (LangGraph-based).

This package implements the multi-step workflow that takes an arbitrary Excel
file uploaded by a user, detects which Trufiq entity it describes (parcelas,
gastos, ingresos), proposes a column mapping via OpenAI, lets the user resolve
ambiguities, transforms and validates the data locally, and finally generates
a CSV suitable for ``app.services.import_service``.

Modules:
    state            - OnboardingState TypedDict (graph state)
    entity_schemas   - Target schemas for the supported entities
    excel_parser     - openpyxl-based Excel parser
    llm_nodes        - LangGraph nodes that call the LLM (Fase 1)
    transform_nodes  - Local data transformation (Fase 3)
    validate_nodes   - Business-rule validation (Fase 3)
    csv_writer       - CSV generation matching import_service formats (Fase 3)
    agent            - LangGraph workflow assembly (Fase 1)
"""
