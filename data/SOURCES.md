# Public sources

Only primary sources (hostinger.com) are used. Marketing pages were read on **10 November 2026**, product pages (Reach, Mail, referral programme) on **13 November 2026**.
Every figure below is used only to **calibrate the SIMULATED data**. No Hostinger customer, order, marketing or product-usage data is used anywhere in this project.

| # | Fact used in the simulation | Quote (short) | Source |
|---|---|---|---|
| 1 | 30-day money-back guarantee | "may be refunded only if canceled within 30 days of the date of the transaction" | https://www.hostinger.com/legal/refund-policy (revised 29 Oct 2026) |
| 2 | Plans are prepaid for the whole term | "All plans are paid upfront." | https://www.hostinger.com/pricing |
| 3 | Shared/website plan, 48-month intro price and renewal price | "$1.99/mo" (Premium, 85% off) · "Renews at $10.99/mo for the same term." | https://www.hostinger.com/pricing |
| 4 | Cloud plan, 48-month intro price and renewal price | "$7.99/mo" (Cloud Startup) · "Renews at $25.99/mo for the same term." | https://www.hostinger.com/cloud-hosting |
| 5 | VPS plan, 24-month intro price and renewal price | KVM 1 "$6.49/mo" · "Renews at $11.99/mo for the same term." | https://www.hostinger.com/vps-hosting |
| 6 | Website builder priced like the Premium plan | Premium "$1.99/mo", "Renews at $10.99/mo" | https://www.hostinger.com/website-builder |
| 7 | Affiliate commission | "It starts at 40% and grows depending on sales volume." | https://www.hostinger.com/affiliates |
| 8 | No affiliate commission on one-month plans or renewals | "No Commission will be granted for one-month hosting plans, renewal or upgrade of services" | https://www.hostinger.com/legal/affiliate-program-agreement (revised 19 Aug 2026) |
| 9 | Affiliate cookie window (used as the 30-day attribution lookback) | "Every cookie is stored for up to 30 days." | https://www.hostinger.com/legal/affiliate-program-agreement |
| 10 | Commission removed if the sale is refunded | "canceled or refunded by the request of the client during the 45 days period" | https://www.hostinger.com/legal/affiliate-program-agreement |
| 11 | Coupon codes are a known affiliate issue | "You should not use specific coupon codes issued to other Affiliates." | https://www.hostinger.com/legal/affiliate-program-agreement |
| 12 | Revenue-share cap per sale | "the maximum Commission for one sale is $300" | https://www.hostinger.com/legal/affiliate-program-agreement |
| 13 | Company scale (context only, not used in the data) | "Customers worldwide" 5M+ · "Countries served" 150+ · founded "in 2004 in Kaunas, Lithuania" | https://www.hostinger.com/about |

### Product part (read on 13 November 2026)

| # | Fact used in the product simulation | Quote (short) | Source |
|---|---|---|---|
| 14 | Hostinger Reach is an AI e-mail marketing tool | "an AI-powered, beginner-friendly email marketing tool" · "AI writes the copy, builds the layout" | https://www.hostinger.com/reach |
| 15 | Reach plans and the 100-recipient limit of the entry plan (used as the free limit that triggers an upgrade) | Starter "$1.49/mo", 100 recipients, 200 emails/mo · Grow "$1.74/mo", 500 recipients | https://www.hostinger.com/reach |
| 16 | Reach scale (context only) | "304K+ marketers trust Reach" · "240K+ campaigns created with AI" | https://www.hostinger.com/reach |
| 17 | Some hosting plans include Reach for free (why hosting customers start Reach onboarding) | "Free AI email marketing for 1 year up to 100 subscribers" | https://www.hostinger.com/horizons (AI Builder page) |
| 18 | Hostinger Mail (business e-mail) has AI replies | "AI writes, replies, and summarizes your emails" · "Smart AI-driven email replies" | https://www.hostinger.com/business-email |
| 19 | Referral reward for the referrer | "You'll receive 20% of the purchase price of each eligible sale." · "Earn up to 450 USD" | https://www.hostinger.com/referral-program |
| 20 | Discount for the referred friend | "They'll enjoy 20% off too!" | https://www.hostinger.com/referral-program |
| 21 | Reward paid only after the refund window | "use the services for 45+ days" (30-day guarantee + 15 days) | https://www.hostinger.com/referral-program |
| 22 | Eligible products include e-mail and e-mail marketing | "hosting, VPS, ... email, email marketing or Hostinger AI Builder plan" | https://www.hostinger.com/referral-program |
| 23 | Referral programme scale (context only) | "75K+ Active members" · "315K+ Successful referrals" | https://www.hostinger.com/referral-program |


## Notes
- Prices on the pricing pages were **Black Friday promotions** on the day they were read. The simulation uses them as the intro price for the longest term and treats shorter-term prices as assumptions (see `ASSUMPTIONS.md`).
- Prices are in USD on the site. The simulation converts them at an assumed **0.87 EUR per USD**.
- 1-month and 12-month plans are not shown on the fetched pricing page; their existence is implied by the affiliate agreement ("one-month hosting plans"). Their prices are **assumptions**.
- Nothing here describes Hostinger's real channel mix, spend, conversion or refund rates. Those are **assumptions**, listed in `ASSUMPTIONS.md`.
- The referral page does not state a rule against self-referral; the self-referral checks in `sql/11_referral_program.sql` are a standard control proposed by this study, not a quoted Hostinger rule.
- Reach, Mail and referral **usage** (funnel rates, retention, AI adoption, referral volumes, fraud) is **simulated**. The public pages only give product features, plan limits and programme terms.
- Hostinger Horizons now redirects to the Hostinger AI Builder page ("merging our website builder and Horizons into a single builder"); it is used for fact #17 only.
