# Middle East Conflict Economic Impact Test Design

## Overview

A comprehensive comparison test analyzing how Middle East conflicts impact the world economy, covering energy markets, supply chains, and financial markets.

## Test Structure

```
Middle East Economic Impact Test
├── Energy Markets (5 web_search + 2 web_fetch)
├── Supply Chain (5 web_search + 2 web_fetch)
└── Financial Markets (5 web_search + 2 web_fetch)
```

## Web Search Queries (15 total)

### Energy Markets
| Query | Expected Keywords |
|-------|------------------|
| "oil price Middle East conflict 2024" | oil, price, conflict |
| "OPEC production cut Middle East" | OPEC, production, cut |
| "natural gas Europe supply disruption" | gas, Europe, supply |
| "crude oil shipping routes Red Sea" | shipping, Red Sea, routes |
| "Saudi Arabia Iran tension oil market" | Saudi, Iran, tension |

### Supply Chain
| Query | Expected Keywords |
|-------|------------------|
| "Red Sea shipping crisis 2024" | shipping, crisis, Red Sea |
| "container shipping costs Middle East war" | container, costs, war |
| "global supply chain disruption insurance" | supply chain, insurance |
| "Maersk shipping route change" | Maersk, route, change |
| "Semiconductor supply chain Middle East" | semiconductor, supply |

### Financial Markets
| Query | Expected Keywords |
|-------|------------------|
| "oil price impact stock market 2024" | oil, stock, market |
| "gold price Middle East conflict" | gold, price, conflict |
| "dollar index Middle East war" | dollar, index, war |
| "Treasury yields Middle East" | Treasury, yields |
| "emerging markets Middle East exposure" | emerging, markets, exposure |

## Web Fetch URLs (6 total)

### Energy Markets
| URL | Expected Keywords |
|-----|------------------|
| https://www.reuters.com/business/energy | oil, energy, OPEC |
| https://www.iea.org/topics/oil | oil, supply, demand |

### Supply Chain
| URL | Expected Keywords |
|-----|------------------|
| https://www.mckinsey.com/industries/travel-logistics | shipping, supply chain |
| https://www.bloomberg.com/topics/supply-chain | supply, disruption |

### Financial Markets
| URL | Expected Keywords |
|-----|------------------|
| https://www.ft.com/markets/commodities | commodities, oil, gold |
| https://www.cnbc.com/investing/ | markets, stocks, bonds |

## Evaluation Metrics

| Metric | Description |
|--------|-------------|
| Keyword Coverage | `expected_keywords` hit rate in output |
| RAG Score | Markdown structure ratio, paragraph count |
| LLM Judge | Accuracy score 1-5 comparing outputs |
| Response Time | Average duration per call |

## Output

- Markdown report: `middle_east_test_report_<timestamp>.md`
- HTML report: `middle_east_test_report_<timestamp>.html`
