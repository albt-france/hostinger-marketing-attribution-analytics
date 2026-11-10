# Simulation assumptions (SIMULATED data)

All data in `data/clean/` is **simulated** by `src/generate_sim.py` (seed 42). It is **not Hostinger data**.
Public facts used for calibration are listed in `SOURCES.md`; everything else below is an **assumption**, chosen to be plausible for a web-hosting brand and to make the analysis meaningful.

## Scope
| Item | Value | Basis |
|---|---|---|
| Period | 1 May 2024 – 31 Oct 2026 (30 months) | assumption (30 months so that 6 monthly cohorts reach 24 months) |
| Countries | US, FR, ES, BR, IN, ID | assumption |
| Demand share by country | US 30%, IN 18%, BR 15%, ID 15%, FR 13%, ES 9% | assumption |
| Regional price index | US/FR/ES 1.0, BR 0.6, IN/ID 0.5 | assumption |
| Seasonality | January ×1.25, September ×1.15, July-August ×0.9, December ×0.85, Black Friday weeks ×1.35 | assumption |

## Products and prices
| Item | Value | Basis |
|---|---|---|
| Products | shared hosting, website builder, cloud, VPS | hostinger.com product pages |
| Longest-term intro price, per month | shared/builder $1.99 (48 m), cloud $7.99 (48 m), VPS $6.49 (24 m) | **public** (SOURCES #3-#6), Black Friday 2026 prices |
| Renewal price, per month | shared/builder $10.99, cloud $25.99, VPS $11.99 | **public** (SOURCES #3-#5) |
| Shorter terms, per month | shared 12 m $2.99, 24 m $2.49; cloud 12 m $11.99, 24 m $9.99; VPS 12 m $7.99 | assumption |
| 1-month plan | priced at the renewal price | assumption |
| Payment | whole term paid upfront | **public** (SOURCES #2) |
| Currency | USD × 0.87 = EUR | assumption |
| Promo codes | 10% off the list price | assumption |
| Renewal | at the end of the term, for 12 months at the renewal price; 1-month plans renew monthly | assumption |

## Channels and journeys
| Item | Value | Basis |
|---|---|---|
| Origins of prospects | PPC non-brand (spend-driven, saturating: prospects ∝ spend^0.65), SEO (growing +40% over the period), influencer videos, content/review affiliates, word of mouth (first touch = brand search), direct, coupon sites | assumption |
| Influencer videos | 40 creators, 227 sponsored videos; prospects ∝ audience^0.8 (fee ∝ audience) | assumption |
| Viewers who click the creator's link | 35%; the others come back through brand search (55%), direct (25%) or a coupon site (20%) | assumption |
| Follow-up visits | 0 to 6 per prospect (mean ~1), channel depends on the origin | assumption |
| Brand search | 60% click the paid ad, 40% the organic result when ads run | assumption |
| Coupon-site visit just before checkout | 5-22% of buyers depending on origin, 80% of them with a cart already started | assumption |
| Leaked codes | 3 large YouTube creators: 15 Jun 2025, 24 Nov 2025, 1 Apr 2026 | assumption |
| Conversion | 5-18% per prospect by origin, +30% per extra visit, capped at 65% | assumption |
| Attribution lookback | 30 days | **public**: affiliate cookie (SOURCES #9) |

## Customer value
| Item | Value | Basis |
|---|---|---|
| Refund window | 30 days | **public** (SOURCES #1) |
| Refund probability | 4% (SEO) to 12% (coupon origin), +5 pts if a coupon site was the last click, +4 pts for 1-month plans | assumption |
| Renewal probability at term end | shared 55%, builder 45%, cloud 65%, VPS 60%, × origin factor (SEO 1.2 … coupon 0.75) | assumption |
| Monthly plan continuation | ~78% per month × origin factor | assumption |

## Spend
| Item | Value | Basis |
|---|---|---|
| PPC non-brand | ~€2,600 a day, budget varied month to month (×0.55-1.5) | assumption |
| PPC brand | clicks × CPC (US €1.10 … IN/ID €0.25) | assumption |
| Influencers | flat fee per video ≈ 3% of audience in EUR (TikTok ×0.7, Instagram ×0.8); CPA €25 per order; hybrid = 40% of flat + €12 | assumption |
| Affiliates | 40-50% of the sale, plans ≥ 12 months only, not on refunded sales, capped at $300 | **public** (SOURCES #7, #8, #10, #12) |
| SEO | €24,000 a month (content team and tools) | assumption |
| E-mail / product marketing | €6,000 a month | assumption |

## Geo test
| Item | Value | Basis |
|---|---|---|
| Design | brand ads off in US, ES, ID for 12 weeks (2 Mar - 24 May 2026); FR, BR, IN as control | assumption |
| Clean baseline | PPC budgets and creator videos frozen from 8 weeks before the test to its end | assumption |
| True effect built in | 15% of would-be ad clickers are lost to competitors' ads on the brand name | assumption (the notebook recovers 14%, 95% CI 5-23%) |

## Planted data-quality issues
| Issue | Where | Found by |
|---|---|---|
| Tracking tag fired twice | all events of 18 Jun 2025 | `07_data_quality.sql`, notebook §5 |
| PPC non-brand cost import failed | 14 Aug 2025 | `07_data_quality.sql` (missing day + 3% invoice gap) |
| Spend rows without campaign id | 60 PPC rows | `07_data_quality.sql` |
| Buyers who declined cookies | 2% of orders, no touchpoint | `07_data_quality.sql` ("Unattributed") |

## Plausibility checks (after generation)
| Ratio | Simulated | Comment |
|---|---|---|
| Prospect → order conversion | 9.9% | prospects are people who visited at least once |
| Orders | 129,431 over 30 months | |
| Average first payment | €63 | most buyers prepay 24 or 48 months at intro prices |
| Plan mix | 1 m 10%, 12 m 23%, 24 m 29%, 48 m 38% | long plans dominate, as the pricing pages push them |
| Refunds within 30 days | 7.5% of orders | |
| Marketing spend | €5.0M (≈ 62% of first-payment revenue) | aggressive acquisition, paid back by renewals |
| Blended cost per order | €39 | |
| Spend mix | PPC non-brand 51%, SEO 14%, influencers 14%, coupon affiliates 9%, content affiliates 6%, brand ads 4%, e-mail 4% | |

The generator prints these checks at the end of each run.
