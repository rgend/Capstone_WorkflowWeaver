import functools

from langgraph.graph import END, StateGraph

from app.graph import nodes
from app.graph.context import RunContext
from app.graph.state import GraphState


def build_graph(ctx: RunContext):
    graph = StateGraph(GraphState)

    graph.add_node("parse_intent", functools.partial(nodes.parse_intent_node, ctx))
    graph.add_node("plan_actions", functools.partial(nodes.plan_actions_node, ctx))
    graph.add_node("execute_step", functools.partial(nodes.execute_step_node, ctx))
    graph.add_node("rollback", functools.partial(nodes.rollback_node, ctx))
    graph.add_node("report", functools.partial(nodes.report_node, ctx))

    graph.set_entry_point("parse_intent")
    graph.add_edge("parse_intent", "plan_actions")
    graph.add_conditional_edges(
        "plan_actions", nodes.route_after_plan, {"execute_step": "execute_step", "report": "report"}
    )
    graph.add_conditional_edges(
        "execute_step",
        nodes.route_after_execute,
        {"execute_step": "execute_step", "rollback": "rollback", "report": "report"},
    )
    graph.add_edge("rollback", "report")
    graph.add_edge("report", END)

    return graph.compile()
