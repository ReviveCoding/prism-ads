SELECT
    treatment,
    count(*) AS rows,
    avg(conversion) AS conversion_rate,
    avg(visit) AS visit_rate,
    avg(exposure) AS exposure_rate
FROM t1_uplift
GROUP BY treatment
ORDER BY treatment;
