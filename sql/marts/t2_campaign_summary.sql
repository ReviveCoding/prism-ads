SELECT
    campaign,
    count(*) AS impressions,
    count(DISTINCT uid) AS users,
    sum(click) AS clicks,
    sum(conversion) AS conversion_impressions,
    sum(cost) AS transformed_cost
FROM t2_attribution
GROUP BY campaign;
