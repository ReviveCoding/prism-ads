SELECT
    treatment,
    count(*) AS rows,
    avg(conversion) AS conversion_rate,
    avg(visit) AS visit_rate,
    avg(exposure) AS exposure_rate
FROM read_parquet('data/validated/t1_uplift_roles.parquet')
GROUP BY treatment
ORDER BY treatment;
