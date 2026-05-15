"""LangGraph definition for the onboarding flow (Fase 1).

The graph currently chains entity detection and column mapping. Phase 3 will
add transform/validate nodes after the human-in-the-loop step.
"""

from __future__ import annotations

from typing import Callable

from langgraph.graph import END, START, StateGraph

from app.services.onboarding.llm_nodes import (
    LLMFactory,
    build_llm,
    detect_entity_node,
    propose_mapping_node,
)
from app.services.onboarding.state import OnboardingState


def build_graph(llm_factory: LLMFactory = build_llm) -> Callable[[OnboardingState], OnboardingState]:
    """Compile the onboarding LangGraph and return its ``invoke`` callable.

    The returned callable accepts an ``OnboardingState`` and returns the
    updated state after running ``detect_entity`` and ``propose_mapping``.
    """
    graph: StateGraph = StateGraph(OnboardingState)
    graph.add_node(
        "detect_entity",
        lambda state: detect_entity_node(state, llm_factory=llm_factory),
    )
    graph.add_node(
        "propose_mapping",
        lambda state: propose_mapping_node(state, llm_factory=llm_factory),
    )
    graph.add_edge(START, "detect_entity")
    graph.add_edge("detect_entity", "propose_mapping")
    graph.add_edge("propose_mapping", END)
    compiled = graph.compile()

    def _run(state: OnboardingState) -> OnboardingState:
        return compiled.invoke(state)  # type: ignore[return-value]

    return _run
