SELECT path_key, count(DISTINCT role) AS role_count
FROM read_parquet('data/validated/t2_attribution_roles.parquet')
GROUP BY path_key
HAVING count(DISTINCT role) > 1;
