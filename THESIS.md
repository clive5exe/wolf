# What WOLF is

**WOLF trades for you.** A model makes the decisions. The app exists to give it
the things a model cannot reach on its own: a broker, market data, filings,
fundamentals, insider activity, and a memory of everything it has already done.
Specialised agents handle the parts they are each good at. Deterministic code
holds the veto so none of it can hurt you.

That is the whole product. Every decision in this repository is downstream of
it, and anything that does not serve it is scope.

## What this is not

**Not a strategy in search of an edge.** WOLF is not an attempt to find a
statistical anomaly that survived thirty years of quant funds. Momentum,
mean-reversion and the rest are *tools the model may reach for*, not the
product. Time spent proving one of them beats the market is time spent on the
wrong problem.

**Not a dashboard.** A dashboard shows you numbers and leaves the work to you.
WOLF does the work and shows you the reasoning.

**Not a backtesting framework.** Backtests validate a fixed rule set. There
isn't one here. What replaces it is the event log: every decision, its
evidence, its verdict and its outcome, replayable, so the system is judged on
its actual record rather than on a simulation of a strategy it does not run.

## Why it can work

The edge is **processing, not prediction**.

Nobody at retail scale reads 1,896 insider filings a day. Nobody reads every
10-K, cross-references the restatements, and checks them against price action.
The information is public, free, and almost entirely unprocessed by individual
investors. Institutions solve this by hiring people. A model collapses that
cost to near zero, and *that* is the asymmetry worth chasing.

We are not betting the model can predict markets. We are betting it can read
more of what is already public than any human competitor bothers to.

## Why it is survivable

Letting a language model act on money is normally reckless. Models hallucinate,
cannot do arithmetic reliably, and can be argued into things. Three properties
make it safe here, and they are already built:

1. **The model has no authority.** It proposes. Twenty-one deterministic rules
   dispose, and they are the sole issuer of an executable order.
2. **It cannot express a dangerous instruction.** The thesis schema has no
   field for size, mode, or autopilot. There is nothing to jailbreak.
3. **Everything is recorded.** Append-only, replayable byte for byte, so a bad
   decision is diagnosable rather than deniable.

The safety work is done. What is missing is giving the model the keys.

## The build, in order

1. **Tool access.** The model currently gets one turn and no tools. It must be
   able to call `get_quote`, `get_fundamentals`, `get_filings`,
   `get_insider_trades`, `get_history`, `screen`, and follow what it finds.
2. **Multiple turns.** Research is looking, forming a question, and looking
   again. One turn makes that impossible.
3. **A schema that proposes.** Today `recommended_action_index` points into a
   list somebody else wrote. The model needs to be able to name a symbol.
4. **Specialised agents.** Separate jobs with separate tools and separate
   prompts: fundamentals, filings and insiders, technicals, and an adversary
   whose only role is to argue the other side before anything reaches risk.
5. **Robinhood, for everything live.** Same venue for data and execution, so
   the price it reasons about is the price it would get.

## The standing rule

If a proposed piece of work does not make the model a better trader or make its
decisions safer to act on, it is not the next thing to build. That includes
work that is interesting, rigorous, and well engineered.
