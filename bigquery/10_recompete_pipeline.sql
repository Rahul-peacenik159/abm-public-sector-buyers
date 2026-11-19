-- 10_recompete_pipeline.sql
-- Agencies with category contracts ending soon, from the shared abm.signals table
-- (load out/signals.jsonl after each run:  bq load --source_format=NEWLINE_DELIMITED_JSON YOUR_PROJECT:abm.signals out/signals.jsonl)

SELECT
  account_domain                                                        AS agency_id,
  ANY_VALUE(tool_name)                                                  AS agency,
  COUNT(DISTINCT IF(signal_type = 'contract_ending_soon', signal_value, NULL))  AS contracts_ending,
  COUNT(DISTINCT IF(signal_type = 'incumbent_competitor', signal_value, NULL))  AS competitor_incumbents,
  COUNT(DISTINCT IF(signal_type = 'open_opportunity', signal_value, NULL))      AS open_opportunities,
  STRING_AGG(DISTINCT IF(signal_type = 'contract_ending_soon', evidence, NULL), ' | ' LIMIT 5) AS ending_detail,
  MAX(observed_at)                                                      AS last_seen
FROM `YOUR_PROJECT.abm.signals`
WHERE pack = 'public-sector-buyers'
  AND observed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY agency_id
ORDER BY open_opportunities DESC, contracts_ending DESC;
