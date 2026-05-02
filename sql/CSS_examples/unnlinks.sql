select
  concat('"', packed_primary_provisional_designation, '": [',
    string_agg(distinct format('"%s"',
      packed_secondary_provisional_designation),
      ','),
    '],') as links
from
  current_identifications
where
  packed_secondary_provisional_designation not in (packed_primary_provisional_designation)
and
  not numbered
/*
and (
  substr(packed_primary_provisional_designation,1,1) not in ('A','C','D','P','S','X')
    or
  substr(packed_primary_provisional_designation,1,3) in ('PLS')
  )
 */
group by
  packed_primary_provisional_designation
order by
  packed_primary_provisional_designation desc;
