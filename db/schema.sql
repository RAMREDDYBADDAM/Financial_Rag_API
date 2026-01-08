 INSERT INTO financial_metrics
(company_id, period, revenue, net_income, operating_income,
 total_assets, total_liabilities, equity, eps)
SELECT id, period, revenue, net_income, operating_income,
       assets, liabilities, assets - liabilities, eps
FROM companies
JOIN (VALUES
('2019-Q1', 58000, 11500, 13500, 340000, 250000, 2.10),
('2019-Q2', 53000, 10000, 12000, 345000, 252000, 1.95),
('2019-Q3', 64000, 13000, 15000, 350000, 255000, 2.30),
('2019-Q4', 92000, 22000, 26000, 355000, 258000, 3.05),

('2020-Q1', 60000, 12000, 14000, 360000, 260000, 2.20),
('2020-Q2', 59000, 11000, 13500, 365000, 262000, 2.05),
('2020-Q3', 67000, 14000, 16500, 370000, 265000, 2.50),
('2020-Q4', 111000, 28000, 32000, 375000, 268000, 4.10),

('2021-Q1', 90000, 23000, 27000, 380000, 270000, 3.60),
('2021-Q2', 82000, 21000, 25000, 385000, 273000, 3.30),
('2021-Q3', 83000, 20500, 24500, 390000, 275000, 3.20),
('2021-Q4', 123000, 34000, 39000, 395000, 278000, 5.30),

('2022-Q1', 97000, 25000, 29000, 400000, 280000, 3.90),
('2022-Q2', 83000, 19500, 23500, 405000, 283000, 3.10),
('2022-Q3', 90000, 22000, 26000, 410000, 285000, 3.45),
('2022-Q4', 118000, 30000, 35000, 415000, 288000, 4.80),

('2023-Q1', 94000, 24000, 28500, 420000, 290000, 3.80),
('2023-Q2', 81000, 19000, 23000, 425000, 292000, 3.00),
('2023-Q3', 89000, 21500, 25500, 430000, 295000, 3.40),
('2023-Q4', 119000, 31000, 36000, 435000, 298000, 4.90)
) AS f(period, revenue, net_income, operating_income, assets, liabilities, eps)
ON TRUE
WHERE ticker = 'AAPL'
ON CONFLICT (company_id, period) DO NOTHING;

INSERT INTO financial_metrics
(company_id, period, revenue, net_income, operating_income,
 total_assets, total_liabilities, equity, eps)
SELECT id, period, revenue, net_income, operating_income,
       assets, liabilities, assets - liabilities, eps
FROM companies
JOIN (VALUES
('2019-Q4', 36000, 11600, 13200, 286000, 184000, 1.55),
('2020-Q4', 43000, 15500, 18000, 300000, 190000, 2.05),
('2021-Q4', 51000, 18700, 22000, 320000, 200000, 2.50),
('2022-Q4', 52000, 16500, 20000, 335000, 205000, 2.35),
('2023-Q4', 56500, 20000, 24500, 355000, 210000, 2.80),
('2024-Q2', 62000, 22500, 27000, 370000, 215000, 3.10)
) AS f(period, revenue, net_income, operating_income, assets, liabilities, eps)
ON TRUE
WHERE ticker = 'MSFT'
ON CONFLICT (company_id, period) DO NOTHING;
INSERT INTO quarterly_reports
(company_id, quarter, year, report_date, summary, highlights)
SELECT id, quarter, year, report_date, summary, highlights
FROM companies
JOIN (VALUES
('Q2', 2024, '2024-05-01',
 'Continued growth driven by Services and regional expansion.',
 'Services revenue +11%, emerging markets growth strong'),

('Q3', 2024, '2024-08-01',
 'Stable demand across product lines despite macro uncertainty.',
 'Wearables steady, supply chain efficiency improved')
) AS r(quarter, year, report_date, summary, highlights)
ON TRUE
WHERE ticker = 'AAPL'
ON CONFLICT (company_id, year, quarter) DO NOTHING;

INSERT INTO products
(company_id, name, description, launch_date, revenue_contribution, status)
SELECT id, name, description, launch_date, revenue_contribution, status
FROM companies
JOIN (VALUES
('Apple Watch', 'Smart wearable device', '2015-04-24', 9.20, 'active'),
('AirPods', 'Wireless audio accessories', '2016-12-13', 7.10, 'active'),
('Apple TV+', 'Subscription streaming service', '2019-11-01', 3.50, 'active')
) AS p(name, description, launch_date, revenue_contribution, status)
ON TRUE
WHERE ticker = 'AAPL'
ON CONFLICT DO NOTHING;
INSERT INTO analyst_ratings
(company_id, analyst_name, firm, rating, price_target, rating_date, rationale)
SELECT id, analyst_name, firm, rating, price_target, rating_date, rationale
FROM companies
JOIN (VALUES
('Mark Lee', 'Morgan Stanley', 'Overweight', 235.00, '2024-04-20',
 'Strong ecosystem lock-in and expanding margins'),

('Sara Chen', 'JP Morgan', 'Buy', 240.00, '2024-06-10',
 'AI-driven services growth expected to accelerate earnings')
) AS a(analyst_name, firm, rating, price_target, rating_date, rationale)
ON TRUE
WHERE ticker = 'AAPL'
ON CONFLICT DO NOTHING;


INSERT INTO market_trends
(sector, trend_date, description, impact_score, source)
VALUES
('Technology', '2024-03-15',
 'Generative AI adoption driving increased cloud infrastructure spending', 9, 'Industry Analysis'),

('Technology', '2024-05-10',
 'Regulatory scrutiny on big tech data usage intensifying', 7, 'Policy Report'),

('E-commerce/Cloud', '2024-04-05',
 'Cloud cost optimization becoming a top CIO priority', 8, 'Market Survey');
