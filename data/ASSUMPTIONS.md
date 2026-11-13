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

---

# Product simulation (SIMULATED data)

All product data is **simulated** by `src/generate_product_sim.py` (seed 42), run after `src/generate_sim.py`. It is **not Hostinger data**.
It uses the **same simulated customers**: same `user_id`, country, device, order date, hosting product and acquisition channel (first click in the 30 days before the order, the rule of `sql/00_staging.sql`), so product use can be cut by marketing channel. Public facts (Reach plans, referral terms) are listed in `SOURCES.md` #14-#23; everything else below is an **assumption**.

## Events (Amplitude-like format)
| Item | Value | Basis |
|---|---|---|
| Table | `sim_product_events`: `event_id`, `user_id`, `device_id`, `event_name`, `event_time`, `product`, `platform`, `country`, `event_properties` (JSON) | Amplitude export format |
| Reach events | `reach_onboarding_started`, `reach_template_chosen`, `reach_contacts_imported`, `reach_campaign_sent`, `reach_ai_copy_used`, `reach_upgrade` | handoff list |
| Mail events | `mail_inbox_opened`, `mail_message_sent`, `mail_ai_reply_used`, logged **once per user and day** with a `count` property (daily roll-up, keeps the file small) | assumption |
| Referral events | `referral_link_shared`, `referral_signup`, `referral_purchase` | handoff list |
| Volume | 2.26M events: Mail 1.78M, Reach 0.46M, referral 17k | generated |
| Window | Reach and referrals 1 May 2025 – 31 Oct 2026; Mail 2 Mar – 25 Oct 2026 | assumption (not Hostinger's launch dates) |
| Latent intent | each customer has an unobserved "intent" (normal); creators +0.30, content sites +0.15, SEO and e-mail +0.10, PPC non-brand −0.15, coupon sites −0.35 | assumption: it drives every Reach step and retention, so the "aha" gap is partly selection |

## Reach onboarding
| Item | Value | Basis |
|---|---|---|
| Who starts onboarding | new customers: 20% (VPS) to 60% (website builder) × channel factor (creators 1.2 … coupon 0.75), a few days after buying; older customers at any time (55% of that); refunded customers ×0.3 | assumption (some plans include Reach for free, SOURCES #17) |
| Newsletter day | 14 Jul 2026: 1,100 extra older customers start onboarding | assumption |
| Steps | template chosen (base 74%), contacts imported (62% of those, −0.35 logit in India and Indonesia), first campaign (68% of those), each step more likely with higher intent | assumption |
| Delays | template ~0.3 day, contacts ~1 day, first campaign ~6 days (shorter with higher intent) | assumption |
| After the first campaign | weekly churn hazard depends on intent **and** on the aha moment (first campaign within 7 days, odds ×e^−0.9); active weeks send 1+ campaigns, 40% with AI copy | assumption |
| Built-in causal part of the aha gap | about **16 points** of day-30 retention for users who reach the aha moment (the observed gap is ~44 points: the rest is selection by intent) | generator printout; the analysis can only see the 44-point correlation |
| Upgrade | 30% of users with more than 100 contacts (above the Starter limit, SOURCES #15), 3% of the others | assumption |

## A/B test
| Item | Value | Basis |
|---|---|---|
| Design | `reach_onboarding_ai_prefill`, users starting onboarding 4 May – 23 Aug 2026, 50/50 | assumption |
| True effect built in | AI-prefilled first campaign: +0.35 logit on choosing a template, first-campaign delay ×0.75: **+5.0 pts** of 7-day activation on the test users (both outcomes of every user are known to the generator) | assumption |
| What the test measures | **+2.5 pts**, 95% CI +0.7 to +4.4 (14 July removed). The gap is chance: without the feature, the users drawn into treatment would have activated **2.1 pts less** than the control users. A single test is one random draw; this one is unlucky (about 1 in 100 at this sample size), which is why the decision keeps a holdout to confirm the effect at scale | generator printout vs notebook |
| Planted bug | on 14 Jul 2026 every mobile user is assigned to control (648 users): sample-ratio mismatch | assumption (the notebook finds it: chi-square p < 0.001, daily z = −19.8) |

## Mail AI replies
| Item | Value | Basis |
|---|---|---|
| Mail users | 5-16% of customers by product (VPS lowest, builder highest), who bought before 2 Mar 2026 | assumption |
| Rollout | wave 1 US, FR, ES on 1 Jun 2026; wave 2 BR, IN, ID on 3 Aug 2026 | assumption (natural control group) |
| Adoption | 40% of mobile users, 30% of desktop users (×1.1 website/hosting) adopt AI replies | assumption |
| True effect built in | adopters on **mobile**: +15% active days and +15% messages; desktop website/hosting: +4% messages; desktop cloud/VPS: none | assumption (the notebook measures +9.5% messages for all mobile users, intention to treat) |

## Referral programme
| Item | Value | Basis |
|---|---|---|
| Reward | 20% of the friend's paid amount, capped at 450 USD (×0.87), voided if refunded, paid after 45 days | **public** (SOURCES #19, #21) |
| Friend's discount | 20%, counted as a programme cost (revenue given up = paid / 0.8 × 0.2); the marketing tables are not changed | **public** rate (SOURCES #20), accounting = assumption |
| Referrers | 5% of customers share a link (more with higher intent), 1.7 shares on average | assumption |
| Referred friends | 3,200 existing simulated orders since 15 May 2025 that arrived by Direct, brand search or SEO with no promo code; referrer from the same country 80% of the time | assumption (keeps refunds and renewals consistent with the marketing part) |
| Planted self-referrals | **420** second accounts (Direct buyers): link shared, sign-up 1-3 minutes later, purchase within the hour; same payment card 75%, same device 85% | assumption (the SQL flags 431, incl. a few households) |
| Households | 3% of genuine friends share the referrer's device, 0.5% the card | assumption (false-positive risk) |
| Scenario (notebook) | genuine referral volume ∝ reward^0.5 or ^1.0; self-referrals ∝ reward^1.5; 30/50/70% of genuine friends truly new | assumption, clearly labelled |

## Plausibility checks (product)
| Ratio | Simulated | Comment |
|---|---|---|
| Customers who start Reach | 35% of all customers (42% of new customers) | |
| Ordered funnel (30-day window) | template 83%, contacts 47%, first campaign 34% | contact import is the biggest drop |
| 7-day activation | 24% of starters | |
| Day-30 retention | 63% (first campaign within 7 days) vs 41% (days 8-30) vs 16% (none) | |
| Referrals | 3,620 in 18 months, rewards + discounts €115k | |

The generator prints these checks at the end of each run.
