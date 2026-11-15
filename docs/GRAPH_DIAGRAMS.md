# GigBid graph diagrams

Generated from the LangGraph builders with `python -m scripts.graphs`.

[Bid graph SVG](images/bid-graph.svg) · [Conversation graph SVG](images/conversation-graph.svg)

## Bid graph

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	intake(intake)
	analyst(analyst)
	risk(risk)
	matcher(matcher)
	reconcile(reconcile)
	pricing(pricing)
	writer(writer)
	verifier(verifier)
	critic(critic)
	compliance(compliance)
	preview(preview)
	regenerate(regenerate)
	approval(approval)
	execute(execute)
	__end__([<p>__end__</p>]):::last
	__start__ --> intake;
	analyst --> reconcile;
	approval -.-> __end__;
	approval -.-> execute;
	approval -.-> regenerate;
	approval -.-> verifier;
	compliance -.-> __end__;
	compliance -.-> preview;
	critic -.-> compliance;
	critic -.-> writer;
	intake -.-> analyst;
	intake -.-> matcher;
	intake -.-> risk;
	matcher --> reconcile;
	preview --> approval;
	pricing -.-> __end__;
	pricing -.-> writer;
	reconcile -.-> __end__;
	reconcile -.-> pricing;
	regenerate --> verifier;
	risk --> reconcile;
	verifier --> critic;
	writer --> verifier;
	execute --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

## Conversation graph

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	intake(intake)
	classify(classify)
	draft(draft)
	verifier(verifier)
	compliance(compliance)
	preview(preview)
	regenerate(regenerate)
	approval(approval)
	execute(execute)
	__end__([<p>__end__</p>]):::last
	__start__ --> intake;
	approval -.-> __end__;
	approval -.-> execute;
	approval -.-> regenerate;
	approval -.-> verifier;
	classify -.-> __end__;
	classify -.-> draft;
	compliance -.-> __end__;
	compliance -.-> preview;
	draft --> verifier;
	intake --> classify;
	preview --> approval;
	regenerate --> verifier;
	verifier --> compliance;
	execute --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```
