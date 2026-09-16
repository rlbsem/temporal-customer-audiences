-- Select revisions at knowledge K BEFORE filtering by business time T.
WITH ranked AS (
  SELECT *,ROW_NUMBER() OVER(PARTITION BY source,fact_id ORDER BY revision DESC) AS r
  FROM facts WHERE person_id=:person AND known_seq<=:known
), visible AS (
  SELECT * FROM ranked WHERE r=1 AND retracted=0
), profile_time AS (
  SELECT MAX(effective_at) AS t FROM visible WHERE source='profile' AND effective_at<=:clock
), profile_now AS (
  SELECT * FROM visible WHERE source='profile' AND effective_at=(SELECT t FROM profile_time)
), boundaries AS (
  SELECT effective_at AS due FROM visible WHERE effective_at>:clock
  UNION ALL SELECT effective_at+:engaged_window FROM visible
    WHERE source='activity' AND value='qualified' AND effective_at<=:clock AND effective_at+:engaged_window>:clock
  UNION ALL SELECT effective_at+:quiet_window FROM visible
    WHERE source='activity' AND value='qualified' AND effective_at<=:clock AND effective_at+:quiet_window>:clock
)
SELECT CASE WHEN (SELECT COUNT(DISTINCT value) FROM profile_now)>1 THEN 'ambiguous'
            ELSE COALESCE((SELECT MIN(value) FROM profile_now),'missing') END AS profile_state,
  (SELECT COUNT(*) FROM visible WHERE source='activity' AND value='qualified'
    AND effective_at>:clock-:engaged_window AND effective_at<=:clock) AS engaged_events,
  (SELECT COUNT(*) FROM visible WHERE source='activity' AND value='qualified'
    AND effective_at>:clock-:quiet_window AND effective_at<=:clock) AS quiet_events,
  (SELECT MIN(due) FROM boundaries) AS next_due,
  (SELECT json_group_array(json_object('source',source,'fact_id',fact_id,'revision',revision,
    'effective_at',effective_at,'value',value)) FROM (
      SELECT source,fact_id,revision,effective_at,value FROM visible
      WHERE (source='profile' AND effective_at=(SELECT t FROM profile_time))
         OR (source='activity' AND value='qualified' AND effective_at<=:clock
             AND effective_at>:clock-MAX(:engaged_window,:quiet_window))
      ORDER BY source,fact_id
  )) AS evidence;
