# What WOLF is

**WOLF trades for you, and the point is to make money.** It is for retail
investors, not for a paper about market structure.

A model makes the decisions. The app exists to give it the things a model
cannot reach on its own: a broker, market data, filings, fundamentals, insider
activity, and a memory of everything it has already done. Specialised agents
handle the parts they are each good at. Deterministic code holds the veto so
none of it can hurt you.

That is the whole product. Every decision in this repository is downstream of
it, and anything that does not serve it is scope.

## What this is not

**Not one hardcoded strategy.** WOLF is absolutely hunting for an edge. What it
is not is a single rule set picked in advance and defended forever. Momentum,
mean-reversion, insider following and the rest are *instruments the model
reaches for*, and the hunt is continuous rather than settled at design time.
Encoding one strategy and calling it the product is the mistake.

**Not a dashboard.** A dashboard shows you numbers and leaves the work to you.
WOLF does the work and shows you the reasoning.

## Why it can work

The edge is **processing, not prediction**.

Nobody at retail scale reads 1,896 insider filings a day. Nobody reads every
10-K, cross-references the restatements, and checks them against price action.
The information is public, free, and almost entirely unprocessed by individual
investors. Institutions solve this by hiring people. A model collapses that
cost to near zero, and *that* is the asymmetry worth chasing.

This is a real edge and it is worth money. We are not betting the model can
predict markets, because nobody can. We are betting it can read more of what is
already public than any other retail participant bothers to, and that acting on
that consistently beats acting on a headline and a hunch.

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

## How we know it works

Backtesting is not optional. Letting a model trade real money without ever
checking what it would have done is not a plan.

It costs money, because judgment cannot be replayed for free: every historical
decision is a real model call. That is a budget constraint, not a reason to
skip it. Three things are testable:

1. **Reconstruct what was knowable on a date, then ask.** Point-in-time data is
   already built: stand on 2023-06-01 and the fundamentals layer returns FY2022,
   never FY2024. Feed the model only that, take its decision, compare to what
   happened.
2. **Replay the deterministic half for free.** Risk, sizing and execution
   already replay byte-identically at zero cost.
3. **Judge the live record.** Every thesis carries an invalidation condition.
   Months of logged decisions say whether they held, which no simulation can.

This is why delisted companies still matter. Offer the model a 2008 universe
with Lehman quietly removed and it looks like a genius for not buying it.

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
